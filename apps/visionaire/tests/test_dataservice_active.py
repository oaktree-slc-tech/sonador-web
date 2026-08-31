'''	Unit tests for inactive Data Service enforcement.

	`AbstractDataService.active` is an authorization boundary: an inactive service rejects
	every service mediated request with HTTP 403 -- introspection (regardless of credential
	validity or the nginx-auth option), the login redirect, the callback, and the token
	exchange (including codes issued before the service was disabled) -- and inactivity
	overrides superuser, staff, and group authorization.
'''
import json

from unittest import mock
from urllib.parse import urlsplit, parse_qs

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from ..auth.models import DataService, SocialAuthorizationServer
from .test_dataservice_redirects import DataServiceOAuthTestCase, REGISTERED


class InactiveServicePermissionTests(TestCase):
	'''	`user_has_perm` returns False for an inactive service before any role check runs.
	'''
	def setUp(self):
		self.dataservice = DataService.objects.create(
			description='Inactive service', active=False)

	def test_inactivity_overrides_superuser(self):
		admin = User.objects.create_user('zofia.marchetti', password='x', is_superuser=True)
		self.assertFalse(self.dataservice.user_has_perm(admin))

	def test_inactivity_overrides_staff(self):
		staff = User.objects.create_user('taavi.kuusk', password='x', is_staff=True)
		self.assertTrue(self.dataservice.acl_allow_staff)
		self.assertFalse(self.dataservice.user_has_perm(staff))

	def test_inactivity_overrides_group_membership(self):
		member = User.objects.create_user('renata.oliveira', password='x')
		group = Group.objects.create(name='integrated-app-users')
		member.groups.add(group)
		self.dataservice.groups.add(group)

		self.assertFalse(self.dataservice.user_has_perm(member))

	def test_active_service_authorization_is_unchanged(self):
		self.dataservice.active = True
		self.dataservice.save()

		staff = User.objects.create_user('joonas.repo', password='x', is_staff=True)
		self.assertTrue(self.dataservice.user_has_perm(staff))


class InactiveServiceUrlPropertyTests(TestCase):
	'''	Defense in depth: an inactive service does not advertise its OAuth endpoints.
	'''
	def setUp(self):
		self.dataservice = DataService.objects.create(
			description='Test service', openid_allow_auth=True)

	def test_active_service_advertises_endpoints(self):
		self.assertTrue(self.dataservice.url_login)
		self.assertTrue(self.dataservice.url_callback)
		self.assertTrue(self.dataservice.url_oidc_token_auth)

	def test_inactive_service_advertises_nothing(self):
		self.dataservice.active = False
		self.dataservice.save()

		self.assertEqual(self.dataservice.url_login, '')
		self.assertEqual(self.dataservice.url_callback, '')
		self.assertEqual(self.dataservice.url_oidc_token_auth, '')


class InactiveOAuthFlowTests(DataServiceOAuthTestCase):
	'''	Login redirect and callback reject an inactive service with 403 before any external
		redirect, authentication, or code creation -- for an otherwise fully authorized
		request (staff user, exact registered redirect URI).
	'''
	def deactivate(self):
		self.dataservice.active = False
		self.dataservice.save()

	def login_url(self):
		'''	Reversed directly: the model url_* properties are blank for inactive services.
		'''
		return reverse('visionaire-api:data-service-openid-login', args=(self.dataservice.pk,))

	def callback_url(self):
		return reverse('visionaire-api:data-service-openid-login-callback', args=(self.dataservice.pk,))

	def test_inactive_login_redirect_returns_403_with_no_idp_redirect(self):
		self.deactivate()

		with mock.patch.object(SocialAuthorizationServer, 'create_authorization_url') as create_url:
			response = self.client.get(self.login_url(), self.login_params())

		self.assertEqual(response.status_code, 403)
		create_url.assert_not_called()

	def test_inactive_noncode_login_redirect_is_also_rejected(self):
		self.deactivate()

		with mock.patch.object(SocialAuthorizationServer, 'create_authorization_url') as create_url:
			response = self.client.get(self.login_url(), {'next': '/'})

		self.assertEqual(response.status_code, 403)
		create_url.assert_not_called()

	def test_inactive_callback_returns_403_and_issues_no_code(self):
		self.deactivate()

		response = self.client.get(self.callback_url(), self.login_params())

		self.assertEqual(response.status_code, 403)
		self.assertNotIn('Location', response)


class InactiveTokenExchangeTests(DataServiceOAuthTestCase):
	'''	The token exchange checks the service's current state, so deactivating the service
		invalidates codes issued while it was active.
	'''
	def setUp(self):
		super(InactiveTokenExchangeTests, self).setUp()

		# The exchange endpoint authorizes session callers who are superusers; the code
		# itself stays bound to the staff user's session on self.client, so the exchange
		# uses a separate client to avoid replacing that session.
		self.api_client = Client()
		self.api_user = User.objects.create_user('ines.baptista', password='x',
			is_staff=True, is_superuser=True)
		self.api_client.force_login(self.api_user)

	def obtain_code(self):
		'''	Run a full login round trip while the service is active and capture the code.
		'''
		self.initiate()
		response = self.client.get(self.dataservice.url_callback, self.login_params())
		self.assertEqual(response.status_code, 302)

		code = parse_qs(urlsplit(response['Location']).query).get('code')
		self.assertTrue(code)
		return code[0]

	def exchange(self, code, **extra):
		'''	The exchange endpoint is a JSON API (integrated clients POST a JSON body).
		'''
		payload = {'client_id': self.dataservice.openid_client_id, 'scope': 'openid',
			'code': code, 'redirect_uri': REGISTERED}
		payload.update(extra)

		return self.api_client.post(
			reverse('visionaire-api:data-service-openid-token', args=(self.dataservice.pk,)),
			{ key: val for key, val in payload.items() if val is not None },
			content_type='application/json')

	def test_exchange_succeeds_while_the_service_is_active(self):
		'''	Control: proves the exchange harness works, so the inactive 403 below is the
			guard rather than a broken request.
		'''
		response = self.exchange(self.obtain_code())

		self.assertEqual(response.status_code, 200)
		self.assertIn(b'token', response.content)

	def test_a_code_can_only_be_redeemed_once(self):
		'''	Redemption records the code's transaction identifier, so presenting the same code
			again within its lifetime is refused.
		'''
		code = self.obtain_code()

		self.assertEqual(self.exchange(code).status_code, 200)

		replayed = self.exchange(code)
		self.assertEqual(replayed.status_code, 403)
		self.assertNotIn(b'"token"', replayed.content)

	def test_a_code_cannot_be_redeemed_for_a_different_redirect_uri(self):
		'''	The code is bound to the callback it was issued against.
		'''
		response = self.exchange(self.obtain_code(),
			redirect_uri='https://viewer.example.com:8443/other/callback')

		self.assertEqual(response.status_code, 403)
		self.assertNotIn(b'"token"', response.content)

	def test_the_matching_redirect_uri_is_accepted(self):
		response = self.exchange(self.obtain_code(), redirect_uri=REGISTERED)

		self.assertEqual(response.status_code, 200)
		self.assertIn(b'token', response.content)

	def test_a_missing_redirect_uri_is_refused(self):
		'''	The binding is mandatory: a code cannot be redeemed without naming the callback
			it was issued against.
		'''
		response = self.exchange(self.obtain_code(), redirect_uri=None)

		self.assertIn(response.status_code, (400, 403))
		self.assertNotIn(b'"token"', response.content)

	def test_a_mismatched_client_id_is_refused(self):
		for variant in ('other-client', self.dataservice.openid_client_id.lower(),
				'%sx' % self.dataservice.openid_client_id):
			if variant == self.dataservice.openid_client_id:
				continue

			response = self.exchange(self.obtain_code(), client_id=variant)
			self.assertIn(response.status_code, (400, 403),
				'client_id "%s" was accepted' % variant)
			self.assertNotIn(b'"token"', response.content)

	def test_redemption_is_refused_when_the_claim_cannot_be_recorded(self):
		'''	A failure to record the redemption denies issuance rather than issuing a token
			whose redemption was never recorded.
		'''
		code = self.obtain_code()

		with mock.patch('wgtauth.services.views.oauth.SessionStore.save',
				side_effect=Exception('claim storage unavailable')):
			response = self.exchange(code)

		self.assertEqual(response.status_code, 403)
		self.assertNotIn(b'"token"', response.content)

	def test_redemption_performs_no_cache_access(self):
		'''	The claim is a database row, so the flow does not depend on a cache being
			present, shared, or reachable.
		'''
		from django.core.cache import caches, DEFAULT_CACHE_ALIAS
		backend = type(caches[DEFAULT_CACHE_ALIAS])

		code = self.obtain_code()

		with mock.patch.object(backend, 'add', side_effect=AssertionError('cache add')), \
				mock.patch.object(backend, 'get', side_effect=AssertionError('cache get')), \
				mock.patch.object(backend, 'set', side_effect=AssertionError('cache set')):
			response = self.exchange(code)

		self.assertEqual(response.status_code, 200)

	def test_a_preexisting_code_cannot_be_exchanged_after_deactivation(self):
		code = self.obtain_code()

		self.dataservice.active = False
		self.dataservice.save()

		response = self.exchange(code)

		self.assertEqual(response.status_code, 403)
		self.assertNotIn(b'"token"', response.content)


class InactiveIntrospectionTests(TestCase):
	'''	Credential introspection rejects an inactive service with 403 regardless of
		credential validity and independent of the nginx-auth query option.
	'''
	def setUp(self):
		self.user = User.objects.create_user('milan.horvat', password='x',
			is_staff=True, is_superuser=True)
		self.client.force_login(self.user)

		self.dataservice = DataService.objects.create(description='Test service')
		self.url = reverse('visionaire-api:data-service-token-introspect',
			args=(self.dataservice.pk,))

	def test_active_service_answers_introspection_normally(self):
		'''	With the service active, missing/invalid credentials are a 400 bad request, not a
			403 -- so the 403s below come from the active-state guard.
		'''
		response = self.client.post(self.url, '{}', content_type='application/json')

		self.assertEqual(response.status_code, 400)

	def test_inactive_service_returns_403_without_nginx_auth(self):
		self.dataservice.active = False
		self.dataservice.save()

		self.assertEqual(self.client.post(self.url, '{}', content_type='application/json').status_code, 403)

	def test_inactive_service_returns_403_with_nginx_auth(self):
		self.dataservice.active = False
		self.dataservice.save()

		self.assertEqual(
			self.client.post('%s?nginx-auth=true' % self.url, '{}', content_type='application/json').status_code, 403)

	def test_presented_credentials_are_not_written_to_the_logs(self):
		'''	A credential presented for introspection must not be recorded, whichever provider
			handles it and whether or not it resolves to a user.
		'''
		from .test_dataservice_redirects import capture_logs

		canaries = {
			'bearer': 'Bearer canary-bearer-9f3a2b',
			'session': 'canary-session-7c41de',
			'api-token': 'api-token canary-apitoken-2b88fa',
			'server-token': 'canary-servertoken-51ac07',
		}

		for token_type, token_value in canaries.items():
			with capture_logs() as emitted:
				self.client.post(self.url,
					json.dumps({'token_key': token_type, 'token_value': token_value}),
					content_type='application/json')

			secret = token_value.split()[-1]
			emitted_output = emitted()

			# Fragments as well as the whole value: a partially masked credential still
			# discloses part of what was presented.
			for fragment in (secret, secret[:8], secret[-8:]):
				self.assertNotIn(fragment, emitted_output,
					'the "%s" credential appeared in the logs as "%s"' % (token_type, fragment))
