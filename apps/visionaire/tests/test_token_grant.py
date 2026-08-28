'''	Tests for the oAuth2 authorization code hand-off and token grant redirect.

	Invariants pinned here:

	* the response is appended to the destination's own query, so a registered static query
		and the generated parameters remain distinct;
	* the client's request reaches the token endpoint with its values unchanged;
	* a destination outside this site receives a token only when it matches a complete
		registered callback, and is classified structurally;
	* the registered list is validated against the same names the response generates.
'''
from unittest import mock
from urllib.parse import urlsplit, parse_qs

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from ..auth.models import SocialAuthorizationServer
from ..auth.validators import TOKEN_GRANT_RESPONSE_PARAMS
from ..auth.views.oauth import is_authorized_client_destination
from . import fixtures


ORIGIN = 'https://viewer.example.com'


class TokenGrantRedirectTests(TestCase):

	def setUp(self):
		self.user = User.objects.create_user('agata.wilk', password='x')
		self.client.force_login(self.user)

		self.authserver = fixtures.create_authserver(callback_url='\r\n'.join([
			'%s/callback' % ORIGIN,
			'%s/callback?scope=viewer&tenant=alpha' % ORIGIN,
		]))

	def grant(self, redirect_uri):
		return self.client.get(
			reverse('auth:openid-auth-token', args=(self.authserver.pk,)), {
				'redirect_uri': redirect_uri,
				'scope': 'openid',
				'client_id': self.authserver.client_id,
				'response_type': 'token',
				'state': 'state-token',
			})

	def response_query(self, response):
		self.assertEqual(response.status_code, 302)
		return parse_qs(urlsplit(response['Location']).query)

	def test_a_destination_without_a_query_receives_the_token(self):
		params = self.response_query(self.grant('%s/callback' % ORIGIN))

		self.assertTrue(params.get('access_token'))
		self.assertEqual(params.get('state'), ['state-token'])

	def test_a_registered_static_query_is_preserved_and_kept_distinct(self):
		'''	The registered parameters and the generated ones must arrive as separate query
			parameters, not folded into the last registered value.
		'''
		destination = '%s/callback?scope=viewer&tenant=alpha' % ORIGIN
		response = self.grant(destination)
		params = self.response_query(response)

		# The registered values survive intact rather than absorbing the response
		self.assertEqual(params.get('scope'), ['viewer'])
		self.assertEqual(params.get('tenant'), ['alpha'])

		# The generated values arrive as parameters of their own
		self.assertTrue(params.get('access_token'))
		self.assertEqual(params.get('state'), ['state-token'])

		# One query, extended rather than restarted
		self.assertEqual(response['Location'].count('?'), 1)
		self.assertTrue(response['Location'].startswith('%s&' % destination))


class AuthorizationCodeHandoffTests(TestCase):
	'''	An unauthenticated client asking for a code flow is forwarded to the token endpoint
		by way of the identity provider. The request it made travels as the forwarded state,
		so its values have to arrive unchanged.
	'''
	MIXED_CASE_STATE = 'AbC123XyZ'

	def setUp(self):
		self.authserver = fixtures.create_authserver(
			callback_url='%s/Callback' % ORIGIN)

	def test_the_forwarded_request_keeps_its_case(self):
		'''	The client compares the state it generated when the response returns, and the
			redirect URI path is compared exactly, so normalising the forwarded query would
			break both.
		'''
		destination = '%s/Callback' % ORIGIN

		with mock.patch.object(SocialAuthorizationServer, 'create_authorization_url',
				return_value='https://idp.example.com/o/authorize/') as create_url:
			self.client.get(
				reverse('auth:openid-login', args=(self.authserver.pk,)), {
					'redirect_uri': destination,
					'scope': 'openid',
					'client_id': self.authserver.client_id,
					'response_type': 'code',
					'state': self.MIXED_CASE_STATE,
				})

		self.assertTrue(create_url.called, 'the request was not forwarded')
		forwarded = create_url.call_args[0][1]
		params = parse_qs(urlsplit(forwarded).query)

		self.assertEqual(params.get('state'), [self.MIXED_CASE_STATE])
		self.assertEqual(params.get('redirect_uri'), [destination])
		self.assertEqual(params.get('client_id'), [self.authserver.client_id])


class ExternalDestinationRegistrationTests(TestCase):
	'''	A destination outside this site must match one complete registered callback.
	'''
	REGISTERED = '%s/callback' % ORIGIN
	SECOND = 'https://second.example.com/oauth/return'

	def setUp(self):
		self.user = User.objects.create_user('pavel.novak', password='x')
		self.client.force_login(self.user)

		self.authserver = fixtures.create_authserver(
			callback_url='\r\n'.join([self.REGISTERED, self.SECOND]))

	def grant(self, redirect_uri):
		return self.client.get(
			reverse('auth:openid-auth-token', args=(self.authserver.pk,)), {
				'redirect_uri': redirect_uri,
				'scope': 'openid',
				'client_id': self.authserver.client_id,
				'response_type': 'token',
				'state': 'state-token',
			})

	def assertIssued(self, redirect_uri):
		response = self.grant(redirect_uri)
		self.assertEqual(response.status_code, 302, 'refused: %s' % redirect_uri)
		self.assertIn('access_token', parse_qs(urlsplit(response['Location']).query))

	def assertRefused(self, redirect_uri):
		response = self.grant(redirect_uri)
		self.assertEqual(response.status_code, 403, 'accepted: %s' % redirect_uri)
		self.assertNotIn('Location', response)

	def test_either_registered_entry_is_accepted(self):
		self.assertIssued(self.REGISTERED)
		self.assertIssued(self.SECOND)

	def test_inexact_candidates_are_refused(self):
		'''	Matching is exact in every component, and text occurring inside a registered entry
			is not a match.
		'''
		for candidate in (
				ORIGIN,
				'%s/call' % ORIGIN,
				'%s/callback/extra' % ORIGIN,
				'https://viewer.example.co/callback',
				'https://viewer.example.com:8443/callback',
				'%s/callback?tenant=alpha' % ORIGIN,
				'https://second.example.com/oauth',
				'//viewer.example.com/callback'):
			self.assertRefused(candidate)

	def test_a_malformed_line_invalidates_the_whole_registration(self):
		self.authserver.callback_url = '%s\r\nnot a uri' % self.REGISTERED
		self.authserver.save()

		self.assertRefused(self.REGISTERED)

	def test_missing_registration_refuses_external_destinations(self):
		self.authserver.callback_url = ''
		self.authserver.save()

		self.assertRefused(self.REGISTERED)

	def test_a_destination_declaring_a_generated_name_is_refused(self):
		'''	The client would otherwise receive duplicates and choose between them.
		'''
		for name in ('access_token', 'id_token', 'token_type', 'expires_in', 'state'):
			self.authserver.callback_url = '%s?%s=x' % (self.REGISTERED, name)
			self.authserver.save()

			self.assertRefused('%s?%s=x' % (self.REGISTERED, name))

	def test_an_encoded_generated_name_is_refused(self):
		self.authserver.callback_url = '%s?%s=x' % (self.REGISTERED, 'acc%65ss_token')
		self.authserver.save()

		self.assertRefused('%s?%s=x' % (self.REGISTERED, 'acc%65ss_token'))

	def test_a_refusal_records_no_destination_or_credential(self):
		'''	A refused value is untrusted, and the response carries a credential.
		'''
		from .test_dataservice_redirects import capture_logs

		candidate = 'https://viewer.example.co/callback'

		with capture_logs() as emitted:
			self.assertRefused(candidate)

		self.assertNotIn(candidate, emitted())
		self.assertNotIn('access_token', emitted())


SAME_SITE = 'https://imaging99.oak-tree.us:8070/callback'


class SameSiteDestinationTests(TestCase):
	'''	Registration governs destinations outside this site. A destination belonging to the
		site keeps its existing behaviour, which the viewer relies on.
	'''
	def setUp(self):
		self.user = User.objects.create_user('lena.fischer', password='x')
		self.client.force_login(self.user)

		# Deliberately registers nothing: a same-site destination must not depend on it
		self.authserver = fixtures.create_authserver(callback_url='')

	def grant(self, redirect_uri):
		return self.client.get(
			reverse('auth:openid-auth-token', args=(self.authserver.pk,)), {
				'redirect_uri': redirect_uri,
				'scope': 'openid',
				'client_id': self.authserver.client_id,
				'response_type': 'token',
				'state': 'state-token',
			})

	def test_a_site_destination_is_issued_a_token_without_registration(self):
		response = self.grant(SAME_SITE)

		self.assertEqual(response.status_code, 302)
		self.assertTrue(parse_qs(urlsplit(response['Location']).query).get('access_token'))

	def test_a_site_destination_declaring_a_generated_name_is_still_refused(self):
		'''	The duplicate-parameter rule applies wherever the destination came from.
		'''
		response = self.grant('%s?access_token=x' % SAME_SITE)

		self.assertEqual(response.status_code, 403)
		self.assertNotIn('Location', response)

	def test_an_unregistered_external_destination_is_refused(self):
		'''	Control for the two cases above: with nothing registered, only the site qualifies.
		'''
		response = self.grant('https://viewer.example.com/callback')

		self.assertEqual(response.status_code, 403)


class LoginHandoffAuthorizationTests(TestCase):
	'''	The login redirect forwards to the endpoint which will issue the token, so it applies
		the same destination rule and refuses before the identity provider round trip.
	'''
	REGISTERED = '%s/callback' % ORIGIN

	def setUp(self):
		self.authserver = fixtures.create_authserver(callback_url=self.REGISTERED)

	def login(self, **overrides):
		params = {
			'redirect_uri': self.REGISTERED,
			'scope': 'openid',
			'client_id': self.authserver.client_id,
			'response_type': 'code',
			'state': 'state-token',
		}
		params.update(overrides)

		with mock.patch.object(SocialAuthorizationServer, 'create_authorization_url',
				return_value='https://idp.example.com/o/authorize/') as create_url:
			response = self.client.get(
				reverse('auth:openid-login', args=(self.authserver.pk,)),
				{ k: v for k, v in params.items() if v is not None })

		return response, create_url

	def test_a_registered_destination_is_forwarded(self):
		response, create_url = self.login()

		self.assertEqual(response.status_code, 302)
		self.assertTrue(create_url.called)

	def test_a_site_destination_is_forwarded_without_registration(self):
		response, create_url = self.login(redirect_uri=SAME_SITE)

		self.assertEqual(response.status_code, 302)
		self.assertTrue(create_url.called)

	def test_an_unregistered_destination_is_refused_before_the_provider(self):
		'''	Refusing here means the user is not sent through the identity provider only to be
			rejected on return.
		'''
		response, create_url = self.login(redirect_uri=ORIGIN)

		self.assertEqual(response.status_code, 403)
		create_url.assert_not_called()

	def test_client_id_variants_are_refused(self):
		'''	The client is an identity boundary, so a prefix, suffix, or case variant of the
			real value is not accepted.
		'''
		real = self.authserver.client_id

		for variant in (real[:-1], '%sx' % real, real.lower(), real.upper(), None):
			if variant == real:
				continue

			response, create_url = self.login(client_id=variant)

			self.assertEqual(response.status_code, 403, 'client_id %r was accepted' % variant)
			create_url.assert_not_called()


class SiteClassificationTests(TestCase):
	'''	Whether a destination is this site is decided structurally, by comparing parsed
		network locations rather than by editing the destination.
	'''
	def setUp(self):
		self.user = User.objects.create_user('imre.szabo', password='x')
		self.client.force_login(self.user)
		self.authserver = fixtures.create_authserver(callback_url='')

	def grant(self, redirect_uri):
		return self.client.get(
			reverse('auth:openid-auth-token', args=(self.authserver.pk,)), {
				'redirect_uri': redirect_uri,
				'scope': 'openid',
				'client_id': self.authserver.client_id,
				'response_type': 'token',
				'state': 'state-token',
			})

	SITE = 'https://site.example.org'

	def test_a_host_extending_the_site_host_is_refused(self):
		'''	Site membership is a property of the parsed host, not of how the value begins.
		'''
		with mock.patch('visionaire.auth.views.oauth.site_fullurl', return_value=self.SITE):
			response = self.grant('%s.other.example/callback' % self.SITE)

		self.assertEqual(response.status_code, 403)
		self.assertNotIn('Location', response)

	def test_the_canonical_site_url_is_accepted(self):
		with mock.patch('visionaire.auth.views.oauth.site_fullurl', return_value=self.SITE):
			response = self.grant('%s/callback' % self.SITE)

		self.assertEqual(response.status_code, 302)
		self.assertTrue(parse_qs(urlsplit(response['Location']).query).get('access_token'))

	def test_a_refused_destination_creates_no_credential(self):
		'''	Authorization precedes construction, so nothing is signed for a destination that
			will not receive it.
		'''
		with mock.patch('visionaire.auth.views.oauth.signing.dumps') as dumps:
			response = self.grant('%s/callback' % ORIGIN)

		self.assertEqual(response.status_code, 403)
		dumps.assert_not_called()


class CallbackRegistrationValidationTests(TestCase):
	'''	The registered list is validated against the same names the grant generates, so the
		field cannot accept a registration the request path will later refuse.
	'''
	def authserver(self, callback_url):
		self.created = getattr(self, 'created', 0) + 1
		return fixtures.create_authserver(callback_url=callback_url,
			provider_name='Validation Connect %s' % self.created)

	def test_a_registration_declaring_a_generated_name_is_rejected(self):
		for name in TOKEN_GRANT_RESPONSE_PARAMS:
			server = self.authserver('%s/callback?%s=x' % (ORIGIN, name))

			with self.assertRaises(ValidationError, msg='%s was accepted' % name):
				server.full_clean()

	def test_an_encoded_generated_name_is_rejected(self):
		server = self.authserver('%s/callback?acc%%65ss_token=x' % ORIGIN)

		with self.assertRaises(ValidationError):
			server.full_clean()

	def test_an_unrelated_static_query_is_permitted(self):
		server = self.authserver('%s/callback?tenant=alpha&scope=viewer' % ORIGIN)
		server.full_clean()

	def test_a_name_this_grant_does_not_generate_is_permitted(self):
		'''	The set belongs to this response, not to another flow's.
		'''
		server = self.authserver('%s/callback?code=x' % ORIGIN)
		server.full_clean()

	def test_a_malformed_entry_is_rejected(self):
		server = self.authserver('%s/callback\r\nnot a uri' % ORIGIN)

		with self.assertRaises(ValidationError):
			server.full_clean()


MALFORMED = 'https://[invalid/callback'


class MalformedDestinationTests(TestCase):
	'''	A destination which cannot be parsed is refused on both paths, rather than reaching
		the caller as an error.

		The two endpoints answer differently, and the difference is the contract rather than an
		accident. The grant validates its request through a form whose `redirect_uri` is a
		`URLField`, so syntactically invalid input is a bad request and is answered before any
		authorization question is asked. The login hand-off takes the destination from the query
		directly, so the only judgement available is authorization, and an unparseable value
		cannot be authorized.
	'''
	def setUp(self):
		self.user = User.objects.create_user('nadia.haddad', password='x')
		self.authserver = fixtures.create_authserver(callback_url='%s/callback' % ORIGIN)

	def test_the_helper_refuses_rather_than_raising(self):
		'''	Pinned on the helper because the grant's form rejects malformed input before the
			helper is reached; this is what keeps the login path a refusal and not an error.
		'''
		self.assertFalse(is_authorized_client_destination(MALFORMED, self.authserver,
			reserved_params=TOKEN_GRANT_RESPONSE_PARAMS))

	def test_the_grant_answers_bad_request_and_signs_nothing(self):
		self.client.force_login(self.user)

		with mock.patch('visionaire.auth.views.oauth.signing.dumps') as dumps:
			response = self.client.get(
				reverse('auth:openid-auth-token', args=(self.authserver.pk,)), {
					'redirect_uri': MALFORMED, 'scope': 'openid',
					'client_id': self.authserver.client_id,
					'response_type': 'token', 'state': 'state-token',
				})

		self.assertEqual(response.status_code, 400)
		self.assertNotIn('Location', response)
		dumps.assert_not_called()

	def test_the_grant_refuses_an_unregistered_destination(self):
		'''	A parseable destination is an authorization question, so it is refused rather than
			answered as a bad request. The two outcomes stay distinguishable by cause.
		'''
		self.client.force_login(self.user)

		with mock.patch('visionaire.auth.views.oauth.signing.dumps') as dumps:
			response = self.client.get(
				reverse('auth:openid-auth-token', args=(self.authserver.pk,)), {
					'redirect_uri': 'https://elsewhere.example.net/callback', 'scope': 'openid',
					'client_id': self.authserver.client_id,
					'response_type': 'token', 'state': 'state-token',
				})

		self.assertEqual(response.status_code, 403)
		self.assertNotIn('Location', response)
		dumps.assert_not_called()

	def test_the_login_handoff_refuses_before_the_provider(self):
		with mock.patch.object(SocialAuthorizationServer, 'create_authorization_url') as create_url:
			response = self.client.get(
				reverse('auth:openid-login', args=(self.authserver.pk,)), {
					'redirect_uri': MALFORMED, 'scope': 'openid',
					'client_id': self.authserver.client_id,
					'response_type': 'code', 'state': 'state-token',
				})

		self.assertEqual(response.status_code, 403)
		self.assertNotIn('Location', response)
		create_url.assert_not_called()


class LegacyRegistrationTests(TestCase):
	'''	Rows stored before the field was validated are still held to the request-time rule,
		and both hops apply the same one.
	'''
	def setUp(self):
		self.user = User.objects.create_user('otto.lindqvist', password='x')
		self.authserver = fixtures.create_authserver(callback_url='%s/callback' % ORIGIN)

		# Written without validation, as an existing row would have been
		SocialAuthorizationServer.objects.filter(pk=self.authserver.pk).update(
			callback_url='%s/callback?access_token=x' % ORIGIN)
		self.authserver.refresh_from_db()

		self.destination = '%s/callback?access_token=x' % ORIGIN

	def test_the_login_handoff_refuses_before_the_provider(self):
		with mock.patch.object(SocialAuthorizationServer, 'create_authorization_url') as create_url:
			response = self.client.get(
				reverse('auth:openid-login', args=(self.authserver.pk,)), {
					'redirect_uri': self.destination, 'scope': 'openid',
					'client_id': self.authserver.client_id,
					'response_type': 'code', 'state': 'state-token',
				})

		self.assertEqual(response.status_code, 403)
		create_url.assert_not_called()

	def test_the_grant_refuses_and_signs_nothing(self):
		self.client.force_login(self.user)

		with mock.patch('visionaire.auth.views.oauth.signing.dumps') as dumps:
			response = self.client.get(
				reverse('auth:openid-auth-token', args=(self.authserver.pk,)), {
					'redirect_uri': self.destination, 'scope': 'openid',
					'client_id': self.authserver.client_id,
					'response_type': 'token', 'state': 'state-token',
				})

		self.assertEqual(response.status_code, 403)
		dumps.assert_not_called()
