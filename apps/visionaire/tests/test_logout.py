'''	Unit tests for the OpenID Connect RP-Initiated Logout flow (ohif-viewers#31).

	These exercise the full URL stack with the Django test client rather than calling the view
	directly, because two of the three defects behind the issue lived in URL routing rather than in
	view logic: the end session endpoint answering the wrong HTTP methods, and the post logout
	destination falling through to the `login_required` viewer catch-all.
'''
import json, weakref
from unittest import mock

from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_out
from django.test import TestCase, override_settings
from django.urls import reverse

from guru.helpers import site_fullurl

from ..apisettings import OPENID_AUTH_TOKEN_SESSION_PROVIDER_PARAM, OPENID_AUTH_TOKEN_SESSION_PARAM, \
	OPENID_AUTH_TOKEN_TYPE_SESSION_PARAM
from ..auth.models import SocialAuthorizationServer
from ..auth.signals.events import revoke_openid_access_token
from ..models.branding import SonadorSite
from . import fixtures


LOGOUT_URL = '/accounts/logout'
LOGOUT_SUCCESS_URL = '/accounts/logout/success'
LOGOUT_REDIRECT_URL = '/logout-redirect.html'

SESSION_USER_KEY = '_auth_user_id'


class EndSessionTestCase(TestCase):
	'''	Shared setup: an authenticated session against the end session endpoint.
	'''
	def setUp(self):
		self.user = User.objects.create_user('victor.orlyk', password='x')
		self.client.force_login(self.user)

	def assertSignedOut(self):
		'''	The Django session is the authentication of record -- the token the viewer holds is a
			signed copy of the session key -- so "logged out" means the session no longer
			identifies a user.
		'''
		self.assertNotIn(SESSION_USER_KEY, self.client.session)

	def assertSignedIn(self):
		self.assertIn(SESSION_USER_KEY, self.client.session)


class EndSessionMethodTests(EndSessionTestCase):
	'''	The relying party navigates the top level browsing context to the end session endpoint, so
		it has to answer GET. `django.contrib.auth.views.LogoutView` is POST-only from Django 5.0,
		which answered that navigation with 405 and left the session intact.
	'''

	def test_get_ends_the_session(self):
		self.assertSignedIn()

		response = self.client.get(LOGOUT_URL)

		self.assertEqual(response.status_code, 302)
		self.assertSignedOut()

	def test_post_ends_the_session(self):
		response = self.client.post(LOGOUT_URL)

		self.assertEqual(response.status_code, 302)
		self.assertSignedOut()

	def test_get_is_idempotent_for_an_anonymous_caller(self):
		self.client.logout()

		response = self.client.get(LOGOUT_URL)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response['Location'], LOGOUT_SUCCESS_URL)


class EndSessionRedirectTests(EndSessionTestCase):
	'''	Resolution of `post_logout_redirect_uri`.
	'''

	def test_defaults_to_the_logout_notice(self):
		response = self.client.get(LOGOUT_URL)

		self.assertEqual(response['Location'], LOGOUT_SUCCESS_URL)

	def test_honors_a_relative_sonador_destination(self):
		response = self.client.get(LOGOUT_URL, {'post_logout_redirect_uri': LOGOUT_REDIRECT_URL})

		self.assertEqual(response['Location'], LOGOUT_REDIRECT_URL)
		self.assertSignedOut()

	def test_honors_a_fully_qualified_destination_on_the_requested_host(self):
		destination = 'http://testserver%s' % LOGOUT_REDIRECT_URL

		response = self.client.get(LOGOUT_URL, {'post_logout_redirect_uri': destination})

		self.assertEqual(response['Location'], destination)

	def test_rejects_an_external_destination(self):
		response = self.client.get(LOGOUT_URL,
			{'post_logout_redirect_uri': 'https://evil.example.com/harvest'})

		self.assertEqual(response['Location'], LOGOUT_SUCCESS_URL)

	def test_rejects_a_protocol_relative_destination(self):
		'''	"//host/path" inherits the current scheme and is a classic open redirect vector.
		'''
		response = self.client.get(LOGOUT_URL,
			{'post_logout_redirect_uri': '//evil.example.com/harvest'})

		self.assertEqual(response['Location'], LOGOUT_SUCCESS_URL)

	def test_rejecting_a_destination_still_ends_the_session(self):
		'''	A bad redirect request must not leave the caller signed in.
		'''
		self.client.get(LOGOUT_URL, {'post_logout_redirect_uri': 'https://evil.example.com/harvest'})

		self.assertSignedOut()


class ClientOriginRedirectTests(EndSessionTestCase):
	'''	A viewer that Sonador does not serve itself -- a development server, or a standalone build
		on its own host -- has to be able to finish the logout on its own sign-out page. Registering
		that origin's callback URL with the authorization server is what authorizes it.
	'''
	OTHER_ORIGIN = 'http://viewer.example.com:3000'

	def setUp(self):
		super(ClientOriginRedirectTests, self).setUp()

		self.authserver = fixtures.create_authserver(callback_url='\r\n'.join([
			'%s/callback' % self.OTHER_ORIGIN,
			'%s/silent-refresh.html' % self.OTHER_ORIGIN,
		]))

	def test_sign_out_page_on_a_registered_client_origin_is_honored(self):
		'''	The sign-out page itself is never registered -- the origin is what is trusted.
		'''
		destination = '%s/logout-redirect.html' % self.OTHER_ORIGIN

		response = self.client.get(LOGOUT_URL, {'post_logout_redirect_uri': destination})

		self.assertEqual(response['Location'], destination)
		self.assertSignedOut()

	def test_an_unregistered_origin_is_still_rejected(self):
		'''	Trusting registered origins must not turn the endpoint into an open redirect.
		'''
		response = self.client.get(LOGOUT_URL,
			{'post_logout_redirect_uri': 'http://evil.example.com:3000/logout-redirect.html'})

		self.assertEqual(response['Location'], LOGOUT_SUCCESS_URL)

	def test_a_registered_host_on_another_scheme_is_rejected(self):
		'''	Origin means scheme *and* host, so https://host does not inherit http://host's trust.
		'''
		response = self.client.get(LOGOUT_URL, {
			'post_logout_redirect_uri': 'https://viewer.example.com:3000/logout-redirect.html',
		})

		self.assertEqual(response['Location'], LOGOUT_SUCCESS_URL)

	def test_a_registered_host_on_another_port_is_rejected(self):
		response = self.client.get(LOGOUT_URL, {
			'post_logout_redirect_uri': 'http://viewer.example.com:9999/logout-redirect.html',
		})

		self.assertEqual(response['Location'], LOGOUT_SUCCESS_URL)

	def test_an_origin_registered_on_a_secondary_auth_server_is_honored(self):
		'''	The destination is being validated, not authenticated, so a viewer registered against
			any configured authorization server counts -- not only the default one.
		'''
		secondary = 'https://second.example.com'
		fixtures.create_authserver(
			provider_name='Second Connect', description='Secondary authorization server',
			callback_url='%s/callback' % secondary)

		destination = '%s/logout-redirect.html' % secondary
		response = self.client.get(LOGOUT_URL, {'post_logout_redirect_uri': destination})

		self.assertEqual(response['Location'], destination)

	def test_a_wildcard_callback_origin_covers_its_subdomains(self):
		fixtures.create_authserver(
			provider_name='Wildcard Connect', description='Wildcard authorization server',
			callback_url='https://*.viewers.example.org/callback')

		destination = 'https://research.viewers.example.org/logout-redirect.html'
		response = self.client.get(LOGOUT_URL, {'post_logout_redirect_uri': destination})

		self.assertEqual(response['Location'], destination)

	def test_a_wildcard_callback_origin_does_not_cover_the_bare_domain(self):
		fixtures.create_authserver(
			provider_name='Wildcard Connect', description='Wildcard authorization server',
			callback_url='https://*.viewers.example.org/callback')

		response = self.client.get(LOGOUT_URL, {
			'post_logout_redirect_uri': 'https://viewers.example.org/logout-redirect.html',
		})

		self.assertEqual(response['Location'], LOGOUT_SUCCESS_URL)


class TokenRevocationTests(EndSessionTestCase):
	'''	Ending a session also revokes the identity provider access token Sonador holds on the
		user's behalf, so it does not stay valid at the provider until it expires.

		Revocation is best effort: it must never be able to stop the session flush, which is the
		part that actually signs the user out.
	'''
	ACCESS_TOKEN = 'upstream-access-token'
	TOKEN_TYPE = 'Bearer'

	def setUp(self):
		super(TokenRevocationTests, self).setUp()

		self.authserver = fixtures.create_authserver()
		self.cache_provider_token()

	def cache_provider_token(self, **overrides):
		'''	Mirror what `cache_openid_tokendata` stores after a successful OpenID login.
		'''
		values = {
			OPENID_AUTH_TOKEN_SESSION_PROVIDER_PARAM: self.authserver.pk,
			OPENID_AUTH_TOKEN_SESSION_PARAM: self.ACCESS_TOKEN,
			OPENID_AUTH_TOKEN_TYPE_SESSION_PARAM: self.TOKEN_TYPE,
		}
		values.update(overrides)

		session = self.client.session
		for key, value in values.items():
			if value is None:
				session.pop(key, None)
			else:
				session[key] = value
		session.save()

	def test_logout_revokes_the_provider_token(self):
		with mock.patch.object(SocialAuthorizationServer, 'revoke_authorization_token') as revoke:
			response = self.client.get(LOGOUT_URL)

		self.assertEqual(response.status_code, 302)
		revoke.assert_called_once_with(self.ACCESS_TOKEN, self.TOKEN_TYPE)
		self.assertSignedOut()

	def test_a_failing_provider_does_not_break_logout(self):
		'''	An unreachable or erroring provider must not turn logout into an error page.
		'''
		with mock.patch.object(SocialAuthorizationServer, 'revoke_authorization_token',
				side_effect=Exception('provider unreachable')):
			response = self.client.get(LOGOUT_URL)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response['Location'], LOGOUT_SUCCESS_URL)
		self.assertSignedOut()

	def test_no_revocation_attempted_without_a_cached_token(self):
		'''	Sessions established without an OpenID login have nothing to revoke.
		'''
		self.cache_provider_token(**{OPENID_AUTH_TOKEN_SESSION_PARAM: None})

		with mock.patch.object(SocialAuthorizationServer, 'revoke_authorization_token') as revoke:
			response = self.client.get(LOGOUT_URL)

		self.assertEqual(response.status_code, 302)
		revoke.assert_not_called()
		self.assertSignedOut()

	def test_the_receiver_is_connected(self):
		'''	The handler existed for years but was never registered -- nothing imported the module,
			and it raised ImportError when anything tried. Guard against it silently detaching.
		'''
		# Entry shape varies by Django version (a third `is_async` element was added), so index
		# the receiver rather than unpacking.
		receivers = [entry[1]() if isinstance(entry[1], weakref.ref) else entry[1]
			for entry in user_logged_out.receivers]

		self.assertIn(revoke_openid_access_token, receivers)


class EndSessionStateTests(EndSessionTestCase):
	'''	RP-Initiated Logout 1.0 (section 2): `state` is echoed back to the relying party, but only
		when returning to a destination the relying party asked for.
	'''

	def test_state_is_echoed_to_a_client_destination(self):
		response = self.client.get(LOGOUT_URL, {
			'post_logout_redirect_uri': LOGOUT_REDIRECT_URL,
			'state': 'aB3-xyz_9',
		})

		self.assertIn('state=aB3-xyz_9', response['Location'])

	def test_state_is_not_echoed_to_the_default_destination(self):
		response = self.client.get(LOGOUT_URL, {'state': 'aB3-xyz_9'})

		self.assertEqual(response['Location'], LOGOUT_SUCCESS_URL)

	def test_state_is_not_echoed_when_the_destination_is_rejected(self):
		response = self.client.get(LOGOUT_URL, {
			'post_logout_redirect_uri': 'https://evil.example.com/harvest',
			'state': 'aB3-xyz_9',
		})

		self.assertNotIn('state=', response['Location'])


class PostLogoutPageTests(TestCase):
	'''	Both post logout surfaces must be reachable without a session. Sonador's viewer catch-all is
		wrapped in `login_required`, so a page that is not registered ahead of it sends the
		just-logged-out user back through the OpenID login workflow and signs them straight back in.
	'''

	def test_logout_notice_does_not_require_a_session(self):
		response = self.client.get(LOGOUT_SUCCESS_URL)

		self.assertEqual(response.status_code, 200)

	def test_viewer_sign_out_page_does_not_require_a_session(self):
		response = self.client.get(LOGOUT_REDIRECT_URL)

		self.assertEqual(response.status_code, 200)

	def test_viewer_sign_out_page_accepts_the_extensionless_path(self):
		response = self.client.get('/logout-redirect')

		self.assertEqual(response.status_code, 200)

	def test_viewer_catch_all_still_requires_a_session(self):
		'''	Guards the assertions above: they only mean something while the catch-all is protected.
		'''
		response = self.client.get('/some/viewer/path')

		self.assertEqual(response.status_code, 302)
		self.assertIn(reverse('login'), response['Location'])


class OpenIDConfigurationTests(TestCase):
	'''	The viewer discovers the logout URL from the OpenID configuration document, so the
		published `end_session_endpoint` has to be the endpoint that actually ends sessions.
	'''

	def setUp(self):
		self.user = User.objects.create_user('victor.orlyk', password='x')
		self.client.force_login(self.user)

	def test_end_session_endpoint_points_at_the_logout_view(self):
		response = self.client.get('/auth/openid/.well-known/openid-configuration')

		self.assertEqual(response.status_code, 200)
		self.assertEqual(
			json.loads(response.content)['end_session_endpoint'],
			site_fullurl(reverse('logout')))


@override_settings(AUTH_ENABLED=True)
class ViewerConfigurationTests(TestCase):
	'''	The viewer's OIDC block, as served to the frontend.
	'''

	def oidc_config(self, path='/ohif/config'):
		response = self.client.get(path)

		self.assertEqual(response.status_code, 200)
		return json.loads(response.content)['oidc'][0]

	def test_post_logout_redirect_uri_is_root_relative(self):
		'''	Root relative on purpose: the viewer resolves it against its own origin, so a
			standalone build stays on its own host instead of being dragged to Sonador's. It must
			also stay clear of the viewer's `routerBasename` -- a server scoped viewer would
			otherwise produce "/viewer/<id>/logout-redirect.html", which nothing serves.
		'''
		post_logout_redirect_uri = self.oidc_config()['post_logout_redirect_uri']

		self.assertEqual(post_logout_redirect_uri, reverse('logout-redirect'))
		self.assertTrue(post_logout_redirect_uri.startswith('/'))
		self.assertFalse(post_logout_redirect_uri.startswith('//'))

	def test_end_session_uri_is_published_for_the_logout_fallback(self):
		'''	Used by the header when `signoutRedirect()` cannot start the OpenID logout.
		'''
		self.assertEqual(self.oidc_config()['end_session_uri'], site_fullurl(reverse('logout')))


class FarewellMessageTests(TestCase):
	'''	The viewer's sign-out page renders the site's "Farewell Message", which it retrieves from
		the configuration API. In a multi-site deployment each site carries its own.
	'''

	def branding(self):
		response = self.client.get('/ohif/config')

		self.assertEqual(response.status_code, 200)
		return json.loads(response.content).get('branding') or {}

	def test_the_active_sites_farewell_is_served(self):
		farewell = '# So long\n\nThis site says goodbye its own way.'
		site = SonadorSite.objects.create(
			domain='testserver', name='Test Site', farewell=farewell)

		with override_settings(SITE_ID=site.pk):
			self.assertEqual(self.branding()['farewell'], farewell)

	def test_each_site_gets_its_own_farewell(self):
		'''	Multi-site: the message follows whichever site is active for the request.
		'''
		first = SonadorSite.objects.create(
			domain='first.example.com', name='First', farewell='# First\n\nGoodbye from first.')
		second = SonadorSite.objects.create(
			domain='second.example.com', name='Second', farewell='# Second\n\nGoodbye from second.')

		with override_settings(SITE_ID=first.pk):
			self.assertEqual(self.branding()['farewell'], first.farewell)

		with override_settings(SITE_ID=second.pk):
			self.assertEqual(self.branding()['farewell'], second.farewell)

	def test_falls_back_to_the_platform_default(self):
		'''	A site with no farewell of its own still gets a usable message.
		'''
		site = SonadorSite.objects.create(domain='bare.example.com', name='Bare')

		with override_settings(SITE_ID=site.pk, VIEWER_FAREWELL_MESSAGE='# Bye\n\nPlatform default.'):
			self.assertEqual(self.branding()['farewell'], '# Bye\n\nPlatform default.')
