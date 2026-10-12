'''	Tests for viewers served from an origin other than Sonador's. Such a client never receives
	the Sonador session cookie on its own requests, so it authenticates with the bearer token it
	was granted, and registering its callback with an authorization server is what authorizes it.
'''
from datetime import timedelta
from unittest import mock
from urllib.parse import urlsplit, parse_qs

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core import signing
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ..auth.models import SocialAuthorizationServer
from ..helpers import SESSION_SALT
from . import fixtures


ORIGIN = 'http://viewer.example.com:3000'
SILENT_REFRESH = '%s/silent-refresh.html' % ORIGIN
REFRESH_URL = '/silent-refresh.html'


class SilentAuthenticationTests(TestCase):
	'''	A `prompt=none` request is answered without user interaction.
	'''
	def setUp(self):
		self.authserver = fixtures.create_authserver(callback_url='\r\n'.join([
			'%s/callback' % ORIGIN, SILENT_REFRESH,
		]))

	def authorize(self, **params):
		query = {
			'redirect_uri': SILENT_REFRESH,
			'scope': 'openid',
			'client_id': self.authserver.client_id,
			'response_type': 'code',
			'state': 'state-token',
			'prompt': 'none',
		}
		query.update(params)

		with mock.patch.object(SocialAuthorizationServer, 'create_authorization_url',
				return_value='https://idp.example.com/o/authorize/') as create_url:
			response = self.client.get(
				reverse('auth:openid-login', args=(self.authserver.pk,)), query)

		return response, create_url

	def test_an_anonymous_request_returns_login_required_to_the_client(self):
		response, create_url = self.authorize()

		self.assertEqual(response.status_code, 302)
		location = urlsplit(response['Location'])
		self.assertEqual('%s://%s%s' % (location.scheme, location.netloc, location.path), SILENT_REFRESH)
		self.assertEqual(parse_qs(location.query), {
			'error': ['login_required'], 'state': ['state-token']})
		create_url.assert_not_called()

	def test_an_unregistered_destination_is_refused(self):
		response, create_url = self.authorize(
			redirect_uri='http://other.example.com:3000/silent-refresh.html')

		self.assertEqual(response.status_code, 403)
		self.assertNotIn('Location', response)
		create_url.assert_not_called()

	def test_another_client_id_is_refused(self):
		response, create_url = self.authorize(client_id='another-client')

		self.assertEqual(response.status_code, 403)
		create_url.assert_not_called()

	def test_a_destination_declaring_error_is_refused(self):
		response, create_url = self.authorize(redirect_uri='%s?error=x' % SILENT_REFRESH)

		self.assertEqual(response.status_code, 403)
		create_url.assert_not_called()

	def test_an_authenticated_request_continues_to_the_token_endpoint(self):
		self.client.force_login(User.objects.create_user('ines.duarte', password='x'))

		response, create_url = self.authorize()

		self.assertEqual(response.status_code, 302)
		self.assertTrue(response['Location'].startswith(self.authserver.url_token))
		create_url.assert_not_called()

	def test_an_interactive_request_still_goes_to_the_provider(self):
		response, create_url = self.authorize(prompt='')

		self.assertEqual(response.status_code, 302)
		self.assertTrue(create_url.called)


class BearerTokenRefreshTests(TestCase):
	'''	The refresh endpoint renews the session a bearer token was issued for.
	'''
	def setUp(self):
		self.user = User.objects.create_user('tomas.berg', password='x')
		self.client.force_login(self.user)
		self.session_key = self.client.session.session_key
		self.token = signing.dumps(self.session_key, salt=SESSION_SALT)

		# Requests below carry the bearer token only
		self.client.cookies.clear()

	def refresh(self, authorization=None):
		headers = {'HTTP_AUTHORIZATION': authorization} if authorization else {}
		return self.client.get(REFRESH_URL, **headers)

	def test_a_session_token_is_renewed_for_the_same_session(self):
		response = self.refresh('Bearer %s' % self.token)

		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertEqual(data['token_type'], 'Bearer')
		self.assertEqual(signing.loads(data['access_token'], salt=SESSION_SALT), self.session_key)
		self.assertGreater(data['expires_in'], 0)
		self.assertIn('no-cache', response.get('Cache-Control', ''))

	def test_expiry_reports_the_time_the_session_has_left(self):
		Session.objects.filter(session_key=self.session_key).update(
			expire_date=timezone.now() + timedelta(hours=1))

		expires_in = self.refresh('Bearer %s' % self.token).json()['expires_in']

		self.assertGreater(expires_in, 3500)
		self.assertLessEqual(expires_in, 3600)

	def test_a_token_with_a_bad_signature_is_refused(self):
		response = self.refresh('Bearer %s' % signing.dumps(self.session_key, salt='another-salt'))

		self.assertEqual(response.status_code, 403)

	def test_a_token_for_an_ended_session_is_refused(self):
		Session.objects.filter(session_key=self.session_key).delete()

		response = self.refresh('Bearer %s' % self.token)

		self.assertEqual(response.status_code, 403)

	def test_a_token_for_an_inactive_user_is_refused(self):
		User.objects.filter(pk=self.user.pk).update(is_active=False)

		response = self.refresh('Bearer %s' % self.token)

		self.assertEqual(response.status_code, 403)

	def test_other_credential_types_are_refused(self):
		response = self.refresh('Basic dXNlcjpwYXNz')

		self.assertEqual(response.status_code, 403)

	def test_the_session_cookie_is_still_accepted(self):
		self.client.force_login(self.user)

		response = self.refresh()

		self.assertEqual(response.status_code, 200)
		self.assertEqual(signing.loads(response.json()['access_token'], salt=SESSION_SALT),
			self.client.session.session_key)

	def test_an_anonymous_request_is_sent_to_login(self):
		response = self.refresh()

		self.assertEqual(response.status_code, 302)


@override_settings(CORS_ALLOWED_ORIGINS=[], CORS_ALLOWED_ORIGIN_REGEXES=[], CORS_ALLOW_CREDENTIALS=True)
class RegisteredOriginCorsTests(TestCase):
	'''	Origins registered as authorization server callbacks may make cross-origin requests.
	'''
	def setUp(self):
		fixtures.create_authserver(callback_url='%s/callback' % ORIGIN)

	def preflight(self, origin):
		return self.client.options(REFRESH_URL, HTTP_ORIGIN=origin,
			HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
			HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization')

	def test_a_registered_origin_is_allowed(self):
		response = self.preflight(ORIGIN)

		self.assertEqual(response.get('Access-Control-Allow-Origin'), ORIGIN)
		self.assertEqual(response.get('Access-Control-Allow-Credentials'), 'true')

	def test_an_unregistered_origin_is_not_allowed(self):
		response = self.preflight('http://other.example.com:3000')

		self.assertNotIn('Access-Control-Allow-Origin', response)

	def test_a_registered_host_on_another_port_is_not_allowed(self):
		response = self.preflight('http://viewer.example.com:9999')

		self.assertNotIn('Access-Control-Allow-Origin', response)

	async def test_the_check_runs_under_the_async_handler(self):
		for origin, allowed in ((ORIGIN, True), ('http://other.example.com:3000', False)):
			response = await self.async_client.options(REFRESH_URL, headers={
				'Origin': origin,
				'Access-Control-Request-Method': 'GET',
				'Access-Control-Request-Headers': 'authorization',
			})

			self.assertEqual(response.status_code, 200)
			self.assertEqual(response.get('Access-Control-Allow-Origin'), origin if allowed else None)
