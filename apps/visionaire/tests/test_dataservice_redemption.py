'''	Tests for the authorization code redemption claim.

	A code may be redeemed once. The claim is a row in the session table, whose primary key
	makes the insert a conditional write the database resolves for every worker at once, so
	the property holds across processes without any additional storage.
'''
import threading

from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import connections
from django.core.exceptions import PermissionDenied
from django.test import TestCase, TransactionTestCase, override_settings

from wgtauth.services.views.oauth import authcode_claim_key, claim_authcode_redemption, \
	AUTHCODE_CLAIM_MARKER, SESSION_KEY_MAX_LENGTH

from ..auth.models import DataService
from .test_dataservice_active import InactiveTokenExchangeTests


def create_dataservice(description='Redemption test service'):
	return DataService.objects.create(description=description, openid_allow_auth=True,
		openid_callback_url='https://viewer.example.com/cb')


class ClaimKeyTests(TestCase):
	'''	The key addresses the claim row, so it must be reproducible for the same code and
		unguessable to whoever holds one.
	'''
	def setUp(self):
		self.dataservice = create_dataservice()

	def test_the_key_fits_a_session_key(self):
		key = authcode_claim_key(self.dataservice, 'transaction-1')

		self.assertLessEqual(len(key), SESSION_KEY_MAX_LENGTH)
		self.assertTrue(key.startswith('wgtauth-rc-'))

	def test_the_key_is_deterministic(self):
		self.assertEqual(
			authcode_claim_key(self.dataservice, 'transaction-1'),
			authcode_claim_key(self.dataservice, 'transaction-1'))

	def test_different_transactions_and_services_differ(self):
		other = create_dataservice(description='Second service')

		self.assertNotEqual(
			authcode_claim_key(self.dataservice, 'transaction-1'),
			authcode_claim_key(self.dataservice, 'transaction-2'))
		self.assertNotEqual(
			authcode_claim_key(self.dataservice, 'transaction-1'),
			authcode_claim_key(other, 'transaction-1'))

	def test_the_key_is_secret_derived(self):
		'''	The transaction identifier travels inside the code, so the key must not be
			derivable from it alone.
		'''
		key = authcode_claim_key(self.dataservice, 'transaction-1')

		with override_settings(SECRET_KEY='%s-rotated' % settings.SECRET_KEY):
			rotated = authcode_claim_key(self.dataservice, 'transaction-1')

		self.assertNotEqual(key, rotated)
		self.assertNotIn('transaction-1', key)


class ClaimTests(TestCase):

	def setUp(self):
		self.dataservice = create_dataservice()

	def test_the_first_claim_succeeds_and_the_second_is_refused(self):
		claim_authcode_redemption(self.dataservice, 'transaction-1', 90)

		with self.assertRaises(PermissionDenied):
			claim_authcode_redemption(self.dataservice, 'transaction-1', 90)

	def test_a_missing_transaction_identifier_is_refused(self):
		for transaction_id in (None, ''):
			with self.assertRaises(PermissionDenied):
				claim_authcode_redemption(self.dataservice, transaction_id, 90)

	def test_distinct_codes_claim_independently(self):
		claim_authcode_redemption(self.dataservice, 'transaction-1', 90)
		claim_authcode_redemption(self.dataservice, 'transaction-2', 90)

	def test_the_claim_row_carries_only_a_marker(self):
		'''	The row is readable by anything with session access, so it must hold nothing
			about the user, the credential, or the code.
		'''
		claim_authcode_redemption(self.dataservice, 'transaction-1', 90)

		row = Session.objects.get(
			session_key=authcode_claim_key(self.dataservice, 'transaction-1'))
		decoded = row.get_decoded()

		# The marker, plus Django's own expiry bookkeeping, and nothing else
		self.assertIn(AUTHCODE_CLAIM_MARKER, decoded)
		self.assertEqual(set(decoded) - {AUTHCODE_CLAIM_MARKER, '_session_expiry'}, set())

		# Nothing identifying the user, the code, or the transaction it belongs to
		self.assertNotIn('_auth_user_id', decoded)
		self.assertNotIn('transaction-1', row.session_data)
		self.assertNotIn(str(self.dataservice.pk), row.session_data)

	def test_the_claim_outlives_the_code(self):
		'''	Expiring before the code could stop being presentable would reopen redemption.
		'''
		from django.utils import timezone

		claim_authcode_redemption(self.dataservice, 'transaction-1', 90)
		row = Session.objects.get(
			session_key=authcode_claim_key(self.dataservice, 'transaction-1'))

		self.assertGreater((row.expire_date - timezone.now()).total_seconds(), 30)


class ConcurrentClaimTests(TransactionTestCase):
	'''	The property that matters is decided by the database, so it is exercised with real
		threads on separate connections rather than sequentially.
	'''
	def setUp(self):
		self.dataservice = create_dataservice()

	def test_simultaneous_claims_admit_exactly_one(self):
		claimed, refused, unexpected = [], [], []
		barrier = threading.Barrier(8)

		def attempt():
			barrier.wait()

			try:
				claim_authcode_redemption(self.dataservice, 'transaction-1', 90)
				claimed.append(True)
			except PermissionDenied:
				refused.append(True)
			except BaseException as err:
				# Recorded rather than counted as a refusal: an unrelated failure must not
				# be able to stand in for a rejected replay.
				unexpected.append(repr(err))
			finally:
				connections.close_all()

		threads = [threading.Thread(target=attempt) for _ in range(8)]
		for thread in threads: thread.start()
		for thread in threads: thread.join()

		self.assertEqual(unexpected, [], 'unexpected failures: %s' % unexpected)
		self.assertEqual(len(claimed), 1, 'expected one claim, got %s' % len(claimed))
		self.assertEqual(len(refused), 7)
		self.assertEqual(Session.objects.filter(
			session_key=authcode_claim_key(self.dataservice, 'transaction-1')).count(), 1)


class RedemptionOrderingTests(InactiveTokenExchangeTests):
	'''	A code is spent only by a request which was eligible for a token. Validation of the
		subject the code stands for therefore happens before the claim is recorded, so a
		refused request leaves the code usable.
	'''
	def setUp(self):
		super(RedemptionOrderingTests, self).setUp()

		# Counted as a delta: other tests in the run may leave claim rows behind, so an
		# absolute count would make these assertions depend on execution order.
		self.claims_before = self.claim_rows()

	def claim_rows(self):
		return Session.objects.filter(session_key__startswith='wgtauth-rc-').count()

	def assertClaimsRecorded(self, expected):
		self.assertEqual(self.claim_rows() - self.claims_before, expected)

	def test_an_unresolvable_subject_leaves_the_code_unclaimed(self):
		'''	The session the code stands for is gone, so no user can be resolved.
		'''
		code = self.obtain_code()

		# Only the session the code stands for; the API caller keeps its own.
		Session.objects.filter(session_key=self.client.session.session_key).delete()

		response = self.exchange(code)

		self.assertEqual(response.status_code, 403)
		self.assertClaimsRecorded(0)

	def test_a_revoked_membership_leaves_the_code_unclaimed(self):
		'''	A code held by someone who has lost access is refused, and stays unspent.
		'''
		code = self.obtain_code()

		self.dataservice.acl_allow_staff = False
		self.dataservice.save()

		response = self.exchange(code)

		self.assertEqual(response.status_code, 403)
		self.assertClaimsRecorded(0)

	def test_a_code_refused_for_membership_still_works_once_access_returns(self):
		'''	Because the refusal did not spend it, the code completes when the subject is
			eligible again inside its lifetime.
		'''
		code = self.obtain_code()

		self.dataservice.acl_allow_staff = False
		self.dataservice.save()
		self.assertEqual(self.exchange(code).status_code, 403)

		self.dataservice.acl_allow_staff = True
		self.dataservice.save()

		response = self.exchange(code)

		self.assertEqual(response.status_code, 200)
		self.assertIn(b'token', response.content)
		self.assertClaimsRecorded(1)

	def test_a_successful_exchange_records_exactly_one_claim(self):
		self.assertEqual(self.exchange(self.obtain_code()).status_code, 200)
		self.assertClaimsRecorded(1)
