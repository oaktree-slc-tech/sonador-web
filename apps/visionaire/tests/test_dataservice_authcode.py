'''	Integrity tests for Data Service authorization codes.

	An authorization code is a bearer credential: presenting it yields a Sonador session
	token, and it carries its own authorization claims. Those claims are authenticated with a
	server secret, so a code is only accepted when it was issued by this deployment and has
	not been altered since.
'''
from django.test import TestCase

from wgtauth import hexsigning

from .test_dataservice_active import InactiveTokenExchangeTests


# A key the server does not use. Its value is arbitrary: the property under test is that a
# code authenticated with anything other than the server secret is refused.
FOREIGN_KEY = 'kX7pQ2mV9tR4wL6nB8sD3hF5jA1cZ0yE'


class AuthorizationCodeIntegrityTests(InactiveTokenExchangeTests):
	'''	Reuses the exchange harness: a login round trip issues a real code, which is then
		presented in altered form.
	'''
	def test_a_code_is_not_readable_without_the_server_secret(self):
		'''	The claims are authenticated, so they do not open under another key.
		'''
		code = self.obtain_code()

		with self.assertRaises(Exception):
			hexsigning.loads(code, key=FOREIGN_KEY, max_age=None)

	def test_a_code_authenticated_with_another_key_is_refused(self):
		'''	Only the server secret authenticates a code, so one carrying well formed claims
			under a different key is not accepted.
		'''
		presented = hexsigning.dumps({
			'sub': 'x', 'tenant': 'data-service:%s' % self.dataservice.pk,
			'jti': 'presented-transaction', 'ruri': 'x',
		}, key=FOREIGN_KEY, compress=True)

		response = self.exchange(presented)

		self.assertEqual(response.status_code, 403)
		self.assertNotIn(b'"token"', response.content)

	def test_an_altered_code_is_refused(self):
		'''	Any alteration of a legitimately issued code invalidates it.
		'''
		response = self.exchange('%sx' % self.obtain_code())

		self.assertEqual(response.status_code, 403)
		self.assertNotIn(b'"token"', response.content)

	def test_a_code_is_refused_after_it_has_been_redeemed(self):
		'''	Redemption is recorded, so the same code presented again is refused.
		'''
		code = self.obtain_code()
		self.assertEqual(self.exchange(code).status_code, 200)

		response = self.exchange(code)

		self.assertEqual(response.status_code, 403)
		self.assertNotIn(b'"token"', response.content)
