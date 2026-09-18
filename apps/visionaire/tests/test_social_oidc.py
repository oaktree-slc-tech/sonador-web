'''	Tests for the request protections of the social (identity provider) login round trip:
	server side state, PKCE, nonce, and ID token verification.

	The login redirect records the login against a generated state instead of sending the
	destination through the identity provider as the state, so every consumer which forwards
	a request through that state -- the plain `next` redirect, the OHIF authorization code
	hand-off, and the data service code flow -- still lands on the same destination, read
	back from the session rather than from the provider's response.

	The identity provider is not contacted: the token exchange and the user lookup are the
	package's own request helpers, patched to answer as a provider would.
'''
import time

from unittest import mock
from urllib.parse import urlsplit, parse_qs

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from wgtauth.social.models import SocialAppProvider, SocialAuthorizationToken, \
	OPENID_OVERIDE_GLOBALENV
from wgtauth.social.oidc import SESSION_LOGIN_TRANSACTION_KEY, code_challenge
from wgtauth.transactions import TRANSACTION_MAX_AGE

from ..auth.models import SocialAuthorizationServer, SocialUserAccount, DataService
from ..auth.views.oauth import OpenIDLoginCallbackView
from . import fixtures
from .test_dataservice_redirects import REGISTERED


IDP_AUTHORIZE = 'https://idp.example.com:443/o/authorize/'
ISSUER = 'https://idp.example.com/o'

# Key pair standing in for the provider's signing key; the public half is what the key set
# lookup returns.
SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_id_token(nonce=None, audience='test-client-id', key=SIGNING_KEY, algorithm='RS256', **claims):
	'''	ID token as the provider would issue it for the login. A claim passed as None is
		left out of the token.
	'''
	now = int(time.time())
	payload = { 'iss': ISSUER, 'sub': 'idp-user-1', 'aud': audience, 'iat': now, 'exp': now + 300 }
	if nonce is not None:
		payload['nonce'] = nonce
	payload.update(claims)
	payload = { name: val for name, val in payload.items() if val is not None }
	return jwt.encode(payload, key, algorithm=algorithm, headers={'kid': 'k1'})


class ProviderStub(object):
	'''	Answers the token exchange and the user lookup, recording what the package sent.
	'''
	def __init__(self, token_response=None, user_response=None):
		self.token_response = token_response or {'access_token': 'idp-access-token', 'token_type': 'bearer'}
		self.user_response = user_response or {'sub': 'idp-user-1', 'username': 'idp.user',
			'email': 'idp.user@example.com', 'first_name': 'Ida', 'last_name': 'Pointer'}
		self.token_requests = []
		self.revoke_requests = []
		self.user_requests = []

	def post(self, server, rdata, resource=None, auth=None, timeout=None, **kwargs):
		if 'code' in rdata:
			self.token_requests.append(dict(rdata))
			return dict(self.token_response)

		self.revoke_requests.append(dict(rdata))
		return {}

	def get(self, url, params=None, timeout=None, **kwargs):
		self.user_requests.append(dict(params or {}))
		return dict(self.user_response)


class SocialLoginTestCase(TestCase):
	'''	Shared fixture: an authorization server whose provider carries the default
		protections, and the provider stub patched over the package's request helpers.
	'''
	def setUp(self):
		self.authserver = fixtures.create_authserver(callback_url='https://viewer.example.com/Callback')
		self.provider = self.authserver.provider
		self.provider.oidc_issuer = ISSUER
		self.provider.save()
		self.idp = ProviderStub()

		patches = [
			mock.patch('wgtauth.social.models.server_controloperation_post', side_effect=self.idp.post),
			mock.patch('wgtauth.social.models.server_controloperation_get', side_effect=self.idp.get),
			mock.patch('wgtauth.social.oidc.get_jwk_client', return_value=mock.Mock(
				get_signing_key_from_jwt=lambda token: mock.Mock(key=SIGNING_KEY.public_key()))),
		]
		for patcher in patches:
			patcher.start()
			self.addCleanup(patcher.stop)

	def set_policy(self, **flags):
		for name, value in flags.items():
			setattr(self.provider, name, value)
		self.provider.save()

	def login_url(self):
		return reverse('auth:openid-login', args=(self.authserver.pk,))

	def callback_url(self):
		return reverse('auth:openid-login-callback', args=(self.authserver.pk,))

	def initiate(self, **params):
		'''	Run the login redirect and return the query the provider would receive
		'''
		response = self.client.get(self.login_url(), params)
		self.assertEqual(response.status_code, 302)
		self.assertTrue(response['Location'].startswith(IDP_AUTHORIZE), response['Location'])
		return { key: val[0] for key, val in parse_qs(urlsplit(response['Location']).query).items() }

	def pending(self):
		'''	Transactions recorded against the test client's session
		'''
		return dict(self.client.session.get(SESSION_LOGIN_TRANSACTION_KEY) or {})

	def callback(self, state, code='idp-code', **params):
		query = { 'code': code }
		if state is not None:
			query['state'] = state
		query.update(params)
		return self.client.get(self.callback_url(), query)

	def assertLoggedIn(self, response, destination):
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response['Location'], destination)
		self.assertTrue(self.client.session.get('_auth_user_id'))

	def assertRefused(self, response):
		self.assertEqual(response.status_code, 403)
		self.assertNotIn('Location', response)
		self.assertFalse(self.client.session.get('_auth_user_id'))


class LoginRedirectTests(SocialLoginTestCase):
	'''	Initiation: the login is recorded against a generated state and the provider request
		carries the protections the provider record calls for.
	'''
	def test_the_state_is_generated_and_the_destination_recorded(self):
		sent = self.initiate(next='/studylist')

		self.assertTrue(sent.get('state'))
		self.assertNotEqual(sent['state'], '/studylist')
		self.assertGreaterEqual(len(sent['state']), 32)

		record = self.pending()[sent['state']]
		self.assertEqual(record['destination'], '/studylist')
		self.assertEqual(record['redirect_uri'], 'http://testserver%s' % self.callback_url())

	def test_the_provider_request_carries_nonce_and_pkce(self):
		sent = self.initiate()
		record = self.pending()[sent['state']]

		self.assertEqual(sent.get('nonce'), record['nonce'])
		self.assertEqual(sent.get('code_challenge_method'), 'S256')
		self.assertEqual(sent.get('code_challenge'), code_challenge(record['code_verifier']))
		self.assertNotIn('code_verifier', sent)
		self.assertGreaterEqual(len(record['code_verifier']), 43)

	def test_each_login_gets_its_own_state_nonce_and_verifier(self):
		first, second = self.initiate(), self.initiate()
		pending = self.pending()

		self.assertNotEqual(first['state'], second['state'])
		self.assertNotEqual(first['nonce'], second['nonce'])
		self.assertNotEqual(
			pending[first['state']]['code_verifier'], pending[second['state']]['code_verifier'])

	def test_the_forwarded_code_request_is_recorded_as_the_destination(self):
		'''	An OHIF authorization code request is forwarded to the token endpoint with its
			query intact; the forwarded URL is now the recorded destination rather than the
			state sent to the provider.
		'''
		sent = self.initiate(redirect_uri='https://viewer.example.com/Callback', scope='openid',
			client_id=self.authserver.client_id, response_type='code', state='AbC123XyZ')

		self.assertNotEqual(sent['state'], 'AbC123XyZ')
		destination = self.pending()[sent['state']]['destination']
		base, _, query = destination.partition('?')
		self.assertEqual(base, self.authserver.url_token)

		params = parse_qs(query)
		self.assertEqual(params.get('state'), ['AbC123XyZ'])
		self.assertEqual(params.get('redirect_uri'), ['https://viewer.example.com/Callback'])
		self.assertEqual(params.get('client_id'), [self.authserver.client_id])

	def test_pkce_can_be_relaxed(self):
		self.set_policy(oidc_pkce=False)
		sent = self.initiate()

		self.assertNotIn('code_challenge', sent)
		self.assertIsNone(self.pending()[sent['state']]['code_verifier'])
		self.assertTrue(sent.get('nonce'))

	def test_the_nonce_can_be_relaxed(self):
		self.set_policy(oidc_nonce=False)
		sent = self.initiate()

		self.assertNotIn('nonce', sent)
		self.assertIsNone(self.pending()[sent['state']]['nonce'])
		self.assertTrue(sent.get('code_challenge'))

	def test_relaxing_state_restores_the_destination_as_state(self):
		'''	Without state verification nothing is recorded, the destination travels as the
			state, and the protections which depend on the record are not applied.
		'''
		self.set_policy(oidc_state=False)
		sent = self.initiate(next='/studylist')

		self.assertEqual(sent.get('state'), '/studylist')
		self.assertNotIn('nonce', sent)
		self.assertNotIn('code_challenge', sent)
		self.assertEqual(self.pending(), {})

	def test_abandoned_logins_are_bounded(self):
		for _ in range(12):
			self.initiate()
		self.assertLessEqual(len(self.pending()), 8)


class LoginCallbackTests(SocialLoginTestCase):
	'''	Completion: the callback is verified against the recorded login before the code is
		exchanged, and the token response against the login before the user is signed in.
	'''
	def test_a_matching_callback_signs_the_user_in_at_the_recorded_destination(self):
		sent = self.initiate(next='/studylist')
		record = self.pending()[sent['state']]
		self.idp.token_response['id_token'] = make_id_token(nonce=record['nonce'])

		response = self.callback(sent['state'])

		self.assertLoggedIn(response, '/studylist')
		self.assertTrue(User.objects.filter(username='idp.user').exists())
		self.assertTrue(SocialUserAccount.objects.filter(social_user_id='idp.user').exists())

	def test_the_token_exchange_presents_the_recorded_verifier(self):
		sent = self.initiate()
		record = self.pending()[sent['state']]
		self.idp.token_response['id_token'] = make_id_token(nonce=record['nonce'])

		self.callback(sent['state'])

		self.assertEqual(len(self.idp.token_requests), 1)
		exchange = self.idp.token_requests[0]
		self.assertEqual(exchange.get('code_verifier'), record['code_verifier'])
		self.assertEqual(exchange.get('code'), 'idp-code')
		self.assertEqual(exchange.get('redirect_uri'), record['redirect_uri'])

	def test_the_record_is_consumed_so_a_callback_cannot_be_replayed(self):
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(nonce=self.pending()[sent['state']]['nonce'])

		self.assertLoggedIn(self.callback(sent['state']), '/studylist')
		self.client.logout()

		self.assertRefused(self.callback(sent['state']))
		self.assertEqual(len(self.idp.token_requests), 1)

	def test_a_callback_without_state_is_refused_before_the_exchange(self):
		self.initiate()
		self.assertRefused(self.callback(None))
		self.assertEqual(self.idp.token_requests, [])

	def test_a_callback_with_an_unknown_state_is_refused_before_the_exchange(self):
		self.initiate()
		self.assertRefused(self.callback('not-a-state-this-session-issued'))
		self.assertEqual(self.idp.token_requests, [])

	def test_a_state_issued_for_another_server_is_refused(self):
		other = fixtures.create_authserver(provider_name='Other Connect', client_id='other-client')
		sent = self.initiate()

		response = self.client.get(
			reverse('auth:openid-login-callback', args=(other.pk,)), {'code': 'x', 'state': sent['state']})

		self.assertRefused(response)
		self.assertEqual(self.idp.token_requests, [])

	def test_an_expired_record_is_refused(self):
		sent = self.initiate()

		with mock.patch('wgtauth.transactions.time.time', return_value=time.time() + TRANSACTION_MAX_AGE + 1):
			self.assertRefused(self.callback(sent['state']))
		self.assertEqual(self.idp.token_requests, [])

	def test_a_next_parameter_on_the_callback_is_not_the_destination(self):
		'''	The destination is the one recorded when the login started; a value arriving on
			the callback is not read.
		'''
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(nonce=self.pending()[sent['state']]['nonce'])

		self.assertLoggedIn(self.callback(sent['state'], next='/somewhere-else'), '/studylist')

	def test_a_login_without_a_destination_lands_on_the_login_redirect(self):
		sent = self.initiate()
		self.idp.token_response['id_token'] = make_id_token(nonce=self.pending()[sent['state']]['nonce'])

		response = self.callback(sent['state'])

		self.assertEqual(response.status_code, 302)
		self.assertTrue(self.client.session.get('_auth_user_id'))

	def test_an_id_token_with_another_nonce_is_refused(self):
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(nonce='some-other-nonce')

		self.assertRefused(self.callback(sent['state']))
		self.assertEqual(len(self.idp.token_requests), 1)
		self.assertEqual(self.idp.user_requests, [])

	def test_an_id_token_without_a_nonce_is_refused(self):
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token()

		self.assertRefused(self.callback(sent['state']))

	def test_an_id_token_for_another_client_is_refused(self):
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(
			nonce=self.pending()[sent['state']]['nonce'], audience='another-client')

		self.assertRefused(self.callback(sent['state']))

	def test_an_id_token_from_another_issuer_is_refused(self):
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(
			nonce=self.pending()[sent['state']]['nonce'], iss='https://idp.example.com/other')

		self.assertRefused(self.callback(sent['state']))
		self.assertEqual(self.idp.user_requests, [])

	def test_an_id_token_without_an_issuer_is_refused(self):
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(
			nonce=self.pending()[sent['state']]['nonce'], iss=None)

		self.assertRefused(self.callback(sent['state']))

	def test_a_provider_without_a_configured_issuer_refuses_every_id_token(self):
		'''	Fail closed: the issuer is the claim the rest hang off, so a provider which has
			not declared one accepts no ID token at all.
		'''
		self.set_policy(oidc_issuer='')
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(nonce=self.pending()[sent['state']]['nonce'])

		self.assertRefused(self.callback(sent['state']))
		self.assertEqual(self.idp.user_requests, [])

	def test_an_id_token_naming_an_additional_audience_is_refused(self):
		'''	This client trusts no other audience, so a token which also names one is refused
			even when it names this client and its authorized party is this client.
		'''
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(
			nonce=self.pending()[sent['state']]['nonce'],
			audience=['test-client-id', 'another-client'], azp='test-client-id')

		self.assertRefused(self.callback(sent['state']))

	def test_an_id_token_whose_authorized_party_is_another_client_is_refused(self):
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(
			nonce=self.pending()[sent['state']]['nonce'], azp='another-client')

		self.assertRefused(self.callback(sent['state']))

	def test_an_id_token_whose_authorized_party_is_this_client_is_accepted(self):
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(
			nonce=self.pending()[sent['state']]['nonce'], azp='test-client-id')

		self.assertLoggedIn(self.callback(sent['state']), '/studylist')

	def test_an_id_token_signed_with_an_unpermitted_algorithm_is_refused(self):
		'''	The provider permits RS256 by default; a PS256 signature under the same key is
			not accepted until the provider names the algorithm.
		'''
		sent = self.initiate(next='/studylist')
		nonce = self.pending()[sent['state']]['nonce']
		self.idp.token_response['id_token'] = make_id_token(nonce=nonce, algorithm='PS256')

		self.assertRefused(self.callback(sent['state']))

		self.set_policy(oidc_signing_algorithms='RS256, PS256')
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(
			nonce=self.pending()[sent['state']]['nonce'], algorithm='PS256')

		self.assertLoggedIn(self.callback(sent['state']), '/studylist')

	def test_an_id_token_missing_a_required_claim_is_refused(self):
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(
			nonce=self.pending()[sent['state']]['nonce'], sub=None)

		self.assertRefused(self.callback(sent['state']))

	def test_a_profile_without_a_subject_is_refused_before_any_local_account_is_touched(self):
		'''	OpenID Connect Core 5.3.2: the profile is used only when it carries the subject the
			verified ID token names. Without one nothing is looked up, linked, or signed in.
		'''
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(nonce=self.pending()[sent['state']]['nonce'])
		del self.idp.user_response['sub']

		self.assertRefused(self.callback(sent['state']))
		self.assertFalse(User.objects.filter(username='idp.user').exists())
		self.assertFalse(SocialUserAccount.objects.filter(social_user_id='idp.user').exists())

	def test_a_profile_with_another_subject_is_refused_before_any_local_account_is_touched(self):
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(nonce=self.pending()[sent['state']]['nonce'])
		self.idp.user_response['sub'] = 'idp-user-2'

		self.assertRefused(self.callback(sent['state']))
		self.assertFalse(User.objects.filter(username='idp.user').exists())
		self.assertFalse(SocialUserAccount.objects.filter(social_user_id='idp.user').exists())

	def test_a_returning_user_whose_profile_subject_differs_is_not_signed_in(self):
		'''	Binding protects a linked account too: the existing link is not used for a
			profile the ID token was not issued for.
		'''
		existing = User.objects.create_user('idp.user', password='x')
		SocialUserAccount.objects.create(social_provider=self.authserver, user=existing,
			social_user_id='idp.user', email='idp.user@example.com')
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(nonce=self.pending()[sent['state']]['nonce'])
		self.idp.user_response['sub'] = 'idp-user-2'

		self.assertRefused(self.callback(sent['state']))

	def test_the_subject_attribute_follows_the_provider(self):
		'''	A provider whose profile names the subject differently (Facebook returns it as
			`id`) is bound through the attribute it declares.
		'''
		self.set_policy(oidc_subject_attribute='id')
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(nonce=self.pending()[sent['state']]['nonce'])
		del self.idp.user_response['sub']
		self.idp.user_response['id'] = 'idp-user-1'

		self.assertLoggedIn(self.callback(sent['state']), '/studylist')

	def test_a_login_without_an_id_token_is_not_bound(self):
		'''	The OAuth-only path -- no ID token examined -- uses the profile as before.
		'''
		sent = self.initiate(next='/studylist')
		del self.idp.user_response['sub']

		self.assertLoggedIn(self.callback(sent['state']), '/studylist')

	def test_a_token_is_not_examined_when_neither_nonce_nor_token_is_enforced(self):
		'''	With the nonce relaxed and no token required, the policy reads nothing from the
			token response beyond the access token, so a token it could not verify does not
			block the login and no claims are exposed.
		'''
		self.set_policy(oidc_nonce=False, oidc_id_token_required=False)
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = 'not-even-a-jwt'
		del self.idp.user_response['sub']

		with mock.patch.object(OpenIDLoginCallbackView, 'cache_openid_tokendata') as cache:
			response = self.callback(sent['state'])

		self.assertEqual(response.status_code, 302)
		self.assertFalse(hasattr(cache.call_args[0][0], 'id_token_claims'))

	def test_an_expired_id_token_is_refused(self):
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(
			nonce=self.pending()[sent['state']]['nonce'], exp=int(time.time()) - 600)

		self.assertRefused(self.callback(sent['state']))

	def test_a_response_without_an_id_token_signs_in_unless_one_is_required(self):
		sent = self.initiate(next='/studylist')
		self.assertLoggedIn(self.callback(sent['state']), '/studylist')

	def test_a_response_without_an_id_token_is_refused_when_one_is_required(self):
		self.set_policy(oidc_id_token_required=True)
		sent = self.initiate(next='/studylist')

		self.assertRefused(self.callback(sent['state']))
		self.assertEqual(self.idp.user_requests, [])

	def test_the_nonce_check_can_be_relaxed(self):
		'''	With the nonce relaxed but the token required, the token is still verified for
			this client; only the nonce binding is not applied.
		'''
		self.set_policy(oidc_nonce=False, oidc_id_token_required=True)
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(nonce='whatever-the-provider-sent')

		self.assertLoggedIn(self.callback(sent['state']), '/studylist')
		self.client.logout()

		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(iss='https://idp.example.com/other')

		self.assertRefused(self.callback(sent['state']))

	def test_the_verified_claims_are_exposed_to_the_integration(self):
		sent = self.initiate(next='/studylist')
		nonce = self.pending()[sent['state']]['nonce']
		self.idp.token_response['id_token'] = make_id_token(nonce=nonce, email='claimed@example.com')

		with mock.patch.object(OpenIDLoginCallbackView, 'cache_openid_tokendata') as cache:
			self.callback(sent['state'])

		authtoken = cache.call_args[0][0]
		self.assertEqual(authtoken.id_token_claims.get('email'), 'claimed@example.com')
		self.assertEqual(authtoken.id_token_claims.get('nonce'), nonce)


class IdTokenSignatureTests(SocialLoginTestCase):
	'''	With a key set declared, the ID token signature is verified against it.
	'''
	def setUp(self):
		super(IdTokenSignatureTests, self).setUp()
		self.set_policy(endpoint_jwks='/o/.well-known/jwks.json')

	def test_a_token_signed_by_the_published_key_is_accepted(self):
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(nonce=self.pending()[sent['state']]['nonce'])

		self.assertLoggedIn(self.callback(sent['state']), '/studylist')

	def test_a_token_signed_by_another_key_is_refused(self):
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(
			nonce=self.pending()[sent['state']]['nonce'], key=OTHER_KEY)

		self.assertRefused(self.callback(sent['state']))
		self.assertEqual(self.idp.user_requests, [])

	def test_a_token_signed_with_a_shared_secret_is_refused(self):
		'''	The key set is public, so a symmetric signature cannot be verified against it
			and is not accepted.
		'''
		sent = self.initiate(next='/studylist')
		now = int(time.time())
		self.idp.token_response['id_token'] = jwt.encode({
			'aud': 'test-client-id', 'exp': now + 300, 'iat': now,
			'nonce': self.pending()[sent['state']]['nonce']}, 'shared-secret', algorithm='HS256')

		self.assertRefused(self.callback(sent['state']))

	def test_without_a_key_set_the_signature_is_not_checked_but_the_issuer_is(self):
		'''	The token exchange's own TLS connection stands in for the signature; the issuer,
			audience, and validity are checked regardless.
		'''
		self.set_policy(endpoint_jwks='')
		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(
			nonce=self.pending()[sent['state']]['nonce'], key=OTHER_KEY)

		self.assertLoggedIn(self.callback(sent['state']), '/studylist')
		self.client.logout()

		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(
			nonce=self.pending()[sent['state']]['nonce'], key=OTHER_KEY, iss='https://idp.example.com/other')

		self.assertRefused(self.callback(sent['state']))

	def test_an_absolute_key_set_location_is_used_as_given(self):
		'''	A provider often publishes its key set on another host than its login endpoints,
			so an absolute location is not resolved against the provider host.
		'''
		self.set_policy(endpoint_jwks='https://keys.example.net/oauth2/v3/certs')
		self.assertEqual(self.authserver.url_jwks, 'https://keys.example.net/oauth2/v3/certs')

		sent = self.initiate(next='/studylist')
		self.idp.token_response['id_token'] = make_id_token(nonce=self.pending()[sent['state']]['nonce'])

		with mock.patch('wgtauth.social.oidc.get_jwk_client', return_value=mock.Mock(
				get_signing_key_from_jwt=lambda token: mock.Mock(key=SIGNING_KEY.public_key()))) as client:
			self.assertLoggedIn(self.callback(sent['state']), '/studylist')

		client.assert_called_once_with('https://keys.example.net/oauth2/v3/certs')

	def test_a_relative_key_set_location_resolves_against_the_provider(self):
		self.assertEqual(self.authserver.url_jwks, 'https://idp.example.com:443/o/.well-known/jwks.json')


class LegacyStateTransportTests(SocialLoginTestCase):
	'''	A provider with state verification off keeps the older behaviour: the destination
		travels as the state and is read back from it.
	'''
	def setUp(self):
		super(LegacyStateTransportTests, self).setUp()
		self.set_policy(oidc_state=False)

	def test_the_destination_is_read_from_the_state(self):
		self.initiate(next='/studylist')
		self.assertLoggedIn(self.callback('/studylist'), '/studylist')
		self.assertNotIn('code_verifier', self.idp.token_requests[0])

	def test_a_callback_without_state_still_signs_in(self):
		response = self.callback(None)
		self.assertEqual(response.status_code, 302)
		self.assertTrue(self.client.session.get('_auth_user_id'))


class ProviderOverrideCompatibilityTests(SocialLoginTestCase):
	'''	Provider records carry their own token exchange as stored Python with the signature
		`get_authorization_token(instance, url_redirect, code)`. The verifier reaches such an
		override through the instance rather than through a new argument, so the stored
		bodies keep working.
	'''
	OVERRIDE = '''
def get_authorization_token(instance, url_redirect, code):
    rdata = instance._authorization_token_request_data(url_redirect, code)
    rdata.update({'client_id': instance.client_id, 'client_secret': instance.client_secret})
    rauth = server_request_post(server_controlurl(instance, instance.endpoint_token), rdata, json_data=False)
    authtoken_data = server_controloperation_json_response(rauth)
    if not authtoken_data.get(instance.authtoken_class.access_token_type_attr):
        authtoken_data[instance.authtoken_class.access_token_type_attr] = 'bearer'
    return instance.authtoken_class(instance, authtoken_data)
'''

	def setUp(self):
		super(ProviderOverrideCompatibilityTests, self).setUp()
		self.provider.get_authorization_token = self.OVERRIDE
		self.provider.save()

		self.posted = []

		def request_post(url, rdata, json_data=False, **kwargs):
			self.posted.append(dict(rdata))
			return mock.Mock()

		globals_patch = mock.patch.dict(OPENID_OVERIDE_GLOBALENV, {
			'server_request_post': request_post,
			'server_controloperation_json_response': lambda response: dict(self.idp.token_response),
		})
		globals_patch.start()
		self.addCleanup(globals_patch.stop)

	def test_the_stored_exchange_receives_the_verifier(self):
		sent = self.initiate(next='/studylist')
		record = self.pending()[sent['state']]
		self.idp.token_response['id_token'] = make_id_token(nonce=record['nonce'])

		self.assertLoggedIn(self.callback(sent['state']), '/studylist')

		self.assertEqual(len(self.posted), 1)
		self.assertEqual(self.posted[0].get('code_verifier'), record['code_verifier'])
		self.assertEqual(self.posted[0].get('client_id'), self.authserver.client_id)


class DataServiceChainTests(SocialLoginTestCase):
	'''	A data service code flow forwards the client's request through the identity provider
		round trip to the data service callback. The forwarded request is now the recorded
		destination, so the chain completes unchanged: the social callback lands on the data
		service callback with the client's query intact, and the code is issued there.
	'''
	def setUp(self):
		super(DataServiceChainTests, self).setUp()
		self.user = User.objects.create_user('mateus.werneck', password='x', is_staff=True)
		self.dataservice = DataService.objects.create(
			description='Test data service', openid_allow_auth=True,
			openid_callback_url=REGISTERED, authserver=self.authserver)
		self.client_request = {
			'response_type': 'code', 'redirect_uri': REGISTERED,
			'client_id': self.dataservice.openid_client_id,
			'state': 'client-state', 'nonce': 'client-nonce',
		}
		# The identity provider answers with the staff user, whose identity is already linked
		self.idp.user_response = {'sub': 'idp-user-1', 'username': 'mateus.werneck', 'email': 'mateus@example.com'}
		SocialUserAccount.objects.create(social_provider=self.authserver, user=self.user,
			social_user_id='mateus.werneck', email='mateus@example.com')

	def test_the_forwarded_request_is_the_recorded_destination(self):
		response = self.client.get(self.dataservice.url_login, self.client_request)
		self.assertEqual(response.status_code, 302)

		sent = { key: val[0] for key, val in parse_qs(urlsplit(response['Location']).query).items() }
		destination = self.pending()[sent['state']]['destination']

		base, _, query = destination.partition('?')
		self.assertEqual(base, self.dataservice.url_callback)
		self.assertEqual(parse_qs(query), { key: [val] for key, val in self.client_request.items() })

	def test_the_chain_issues_a_code_to_the_registered_callback(self):
		response = self.client.get(self.dataservice.url_login, self.client_request)
		sent = { key: val[0] for key, val in parse_qs(urlsplit(response['Location']).query).items() }
		self.idp.token_response['id_token'] = make_id_token(nonce=self.pending()[sent['state']]['nonce'])

		# The identity provider answers to the auth server's own callback, which signs the
		# user in and forwards to the recorded destination
		landing = self.callback(sent['state'])
		self.assertEqual(landing.status_code, 302)
		self.assertTrue(landing['Location'].startswith(self.dataservice.url_callback + '?'))

		# The data service callback verifies the client's transaction and issues the code
		issued = self.client.get(landing['Location'])
		self.assertEqual(issued.status_code, 302)
		base, _, query = issued['Location'].partition('?')
		self.assertEqual(base, REGISTERED)

		params = parse_qs(query)
		self.assertTrue(params.get('code'))
		self.assertEqual(params.get('state'), ['client-state'])
		self.assertEqual(params.get('nonce'), ['client-nonce'])


class ProviderImportDefaultsTests(TestCase):
	'''	A provider configuration which does not mention a protection takes the model default
		rather than switching it off, and one which does is honoured.
	'''
	CONFIG = '''[imported]
name = 'Imported Connect'
hostname = 'idp.example.com'
port = 443
scheme = 'https'
description = 'Imported provider'
login_class = 'imported'
endpoint_authorization = '/authorize'
endpoint_token = '/token'
endpoint_token_revoke = '/revoke'
endpoint_user = '/userinfo'
%s
'''

	def import_config(self, extra=''):
		import os, tempfile
		from wgtauth.social.serverconfig.init.database import InitSocialAuthenticationProviders

		root = tempfile.mkdtemp()
		with open(os.path.join(root, 'imported.config'), 'w') as f:
			f.write(self.CONFIG % extra)

		with mock.patch('wgtauth.social.serverconfig.init.database.serverconfigapi.SOCIAL_AUTH_PROVIDER_ROOT', root):
			InitSocialAuthenticationProviders(log=False).run()

		return SocialAppProvider.objects.get(pk='imported')

	def test_omitted_protections_take_the_defaults(self):
		provider = self.import_config()

		self.assertTrue(provider.oidc_state)
		self.assertTrue(provider.oidc_pkce)
		self.assertTrue(provider.oidc_nonce)
		self.assertFalse(provider.oidc_id_token_required)
		self.assertEqual(provider.oidc_signing_algorithms, 'RS256')
		self.assertEqual(provider.oidc_subject_attribute, 'sub')
		self.assertEqual(provider.oidc_issuer, '')
		self.assertEqual(provider.endpoint_jwks, '')

	def test_the_bundled_google_provider_names_its_cross_origin_key_set(self):
		'''	Google publishes its key set on www.googleapis.com while its login endpoints are on
			accounts.google.com; the bundled configuration carries the absolute location and
			the issuer, and the resolved key set URL is that location.
		'''
		import os
		from wgtauth.social.serverconfig import apisettings as serverconfigapi
		from wgtauth.social.serverconfig.init.database import InitSocialAuthenticationProviders

		self.assertTrue(os.path.exists(os.path.join(serverconfigapi.SOCIAL_AUTH_PROVIDER_ROOT, 'google.auth.config')))
		InitSocialAuthenticationProviders(log=False).run()

		provider = SocialAppProvider.objects.get(pk='google')
		self.assertEqual(provider.endpoint_jwks, 'https://www.googleapis.com/oauth2/v3/certs')
		self.assertEqual(provider.oidc_issuer, 'https://accounts.google.com')
		self.assertEqual(provider.oidc_signing_algorithms, 'RS256')
		self.assertTrue(provider.oidc_nonce)

		authserver = SocialAuthorizationServer.objects.create(provider=provider,
			description='Google', client_id='google-client', client_secret='x')
		self.assertEqual(authserver.url_jwks, 'https://www.googleapis.com/oauth2/v3/certs')
		self.assertEqual(authserver.oidc_policy.issuer, 'https://accounts.google.com')

	def test_declared_protections_are_honoured(self):
		provider = self.import_config('oidc_pkce = False\noidc_id_token_required = True\n'
			+ "endpoint_jwks = '/jwks'\n")

		self.assertTrue(provider.oidc_state)
		self.assertFalse(provider.oidc_pkce)
		self.assertTrue(provider.oidc_id_token_required)
		self.assertEqual(provider.endpoint_jwks, '/jwks')
