'''	Per-request site resolution: with `SITE_ID` absent, the request host selects the site and
	every absolute URL handed to the browser is built on that site's configured address, so an
	alternate site keeps its own FQDN and branding through authentication and into the viewer.
	A host which matches no site gets the default site's address and no trust of its own.
'''
import json
from urllib.parse import urlsplit, parse_qs

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sites import models as sites_models
from django.contrib.sites.models import Site
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from ..auth.views.oauth import is_authorized_client_destination
from ..models.branding import SonadorSite
from ..sites import current_site, request_site, site_url
from . import fixtures
from .test_social_oidc import SocialLoginTestCase, make_id_token


PRIMARY = 'primary.example.com'
ALTERNATE = 'alternate.example.com'
ALTERNATE_URL = 'http://%s:8070' % ALTERNATE
CALLBACK = 'https://viewer.example.com/Callback'

# Destinations off every Sonador site: other hosts, lookalikes of the site address (extended
# host, userinfo, the site URL in a path), backslash spellings browsers read as a host, part of
# a registered callback, and the site on a port it is not configured for
OFF_SITE = (
	'https://evil.example.net/',
	'%s.evil.example.net/' % ALTERNATE_URL,
	'http://%s:8070@evil.example.net/' % ALTERNATE,
	'http://evil.example.net/%s/' % ALTERNATE_URL,
	'/\\evil.example.net/',
	'\\\\evil.example.net/',
	'http:\\\\evil.example.net/',
	'https://viewer.example.com/Call',
	'https://viewer.example.com',
	'http://%s:9999/viewer/' % ALTERNATE,
)

# Wildcard entries only, so no host is trusted because ALLOWED_HOSTS names it exactly
SITE_SETTINGS = dict(DEFAULT_SITE_ID=None, ALLOWED_HOSTS=['.example.com', 'testserver'],
	SITE_CONNECT_SCHEME='http', SITE_CONNECT_PORT='8070',
	SITE_CONNECT_MATCH_SITE_SCHEME=False, SITE_CONNECT_MATCH_SITE_NETLOC=False)


class SiteSettingsMixin(object):
	'''	Sites configured for per-host resolution, with `SITE_ID` genuinely absent
	'''
	def setUp(self):
		super().setUp()
		_override = override_settings(SITE_ID=1, **SITE_SETTINGS)
		_override.enable()
		self.addCleanup(_override.disable)
		del settings.SITE_ID

		Site.objects.clear_cache()
		self.primary = SonadorSite.objects.create(domain=PRIMARY, name='Primary', welcome='# Primary welcome')
		self.alternate = SonadorSite.objects.create(domain=ALTERNATE, name='Alternate',
			welcome='# Alternate welcome')
		self.default = Site.objects.order_by('pk').first()
		self.factory = RequestFactory()

	def request(self, host):
		return self.factory.get('/', HTTP_HOST=host)


class SiteResolutionTests(SiteSettingsMixin, TestCase):

	def test_the_setting_is_absent(self):
		self.assertFalse(hasattr(settings, 'SITE_ID'))

	def test_site_follows_the_request_host(self):
		self.assertEqual(current_site(self.request('%s:8070' % ALTERNATE)), self.alternate)
		self.assertEqual(current_site(self.request(PRIMARY)), self.primary)

	def test_unknown_host_gets_the_default_site(self):
		with override_settings(DEFAULT_SITE_ID=self.alternate.pk):
			self.assertEqual(current_site(self.request('alias.example.com')), self.alternate)

	def test_default_site_is_the_first_when_not_configured(self):
		self.assertEqual(request_site(self.request('alias.example.com')), self.default)

	def test_configured_site_id_pins_every_request(self):
		with override_settings(SITE_ID=self.primary.pk):
			_request = self.request('%s:8070' % ALTERNATE)
			self.assertEqual(current_site(_request), self.primary)
			self.assertEqual(site_url('/x', request=_request), 'http://%s:8070/x' % PRIMARY)

	def test_urls_use_the_site_address(self):
		self.assertEqual(site_url('/auth/openid/', request=self.request('%s:8070' % ALTERNATE)),
			'%s/auth/openid/' % ALTERNATE_URL)

	def test_urls_do_not_follow_an_unapproved_port(self):
		self.assertEqual(site_url('/x', request=self.request('%s:9999' % ALTERNATE)), '%s/x' % ALTERNATE_URL)

	def test_an_unmatched_host_gets_the_default_site_address(self):
		'''	Covers a proxy which rewrites Host to an internal name, as well as wildcard hosts
		'''
		with override_settings(DEFAULT_SITE_ID=self.primary.pk):
			self.assertEqual(site_url('/x', request=self.request('internal.example.com')),
				'http://%s:8070/x' % PRIMARY)

	def test_urls_without_a_request_use_the_default_site(self):
		with override_settings(DEFAULT_SITE_ID=self.primary.pk):
			self.assertEqual(site_url('/x'), 'http://%s:8070/x' % PRIMARY)

	def test_viewer_config_carries_the_alternate_site(self):
		fixtures.create_authserver()
		with override_settings(AUTH_ENABLED=True):
			response = self.client.get(reverse('ohif-config'), HTTP_HOST='%s:8070' % ALTERNATE)
		self.assertEqual(response.status_code, 200)
		config = json.loads(response.content)

		self.assertEqual(config['branding']['empty_state'], '# Alternate welcome')
		self.assertEqual(config['sonadorUrl'], ALTERNATE_URL)
		for oidc in config['oidc']:
			self.assertEqual(urlsplit(oidc['authority']).netloc, '%s:8070' % ALTERNATE)
			self.assertEqual(urlsplit(oidc['end_session_uri']).netloc, '%s:8070' % ALTERNATE)

	def test_login_keeps_the_destination(self):
		authserver = fixtures.create_authserver()
		response = self.client.get(reverse('login'), { 'next': '/viewer/?a=1' }, HTTP_HOST='%s:8070' % ALTERNATE)

		self.assertEqual(response.status_code, 302)
		location = urlsplit(response['Location'])
		self.assertEqual(location.path, authserver.url_login)
		self.assertEqual(parse_qs(location.query)['next'], ['/viewer/?a=1'])


class DestinationTrustTests(SiteSettingsMixin, TestCase):
	'''	Credential destinations are trusted from the configured sites, never from the host a
		request happened to arrive on.
	'''
	def trusted(self, destination):
		return is_authorized_client_destination(destination, None)

	def test_a_configured_site_is_trusted(self):
		self.assertTrue(self.trusted('%s/callback' % ALTERNATE_URL))
		self.assertTrue(self.trusted('http://%s:8070/callback' % PRIMARY))

	def test_a_wildcard_host_without_a_site_is_not_trusted(self):
		self.assertFalse(self.trusted('http://anything.example.com:8070/callback'))
		self.assertFalse(self.trusted('http://anything.example.com/callback'))

	def test_an_unapproved_port_is_not_trusted(self):
		self.assertFalse(self.trusted('http://%s:9999/callback' % ALTERNATE))

	def test_a_grant_on_an_unmatched_host_does_not_trust_that_host(self):
		authserver = fixtures.create_authserver(callback_url='')
		user = User.objects.create_user('lena.vogt', password='x')
		client = Client(HTTP_HOST='anything.example.com:8070')
		client.force_login(user)

		response = client.get(reverse('auth:openid-auth-token', args=(authserver.pk,)), {
			'redirect_uri': 'http://anything.example.com:8070/callback', 'scope': 'openid',
			'client_id': authserver.client_id, 'response_type': 'token', 'state': 'state-token'})

		self.assertEqual(response.status_code, 403)
		self.assertNotIn('Location', response)

	def test_an_alternate_site_grant_is_issued(self):
		authserver = fixtures.create_authserver(callback_url='')
		user = User.objects.create_user('ines.rocha', password='x')
		client = Client(HTTP_HOST='%s:8070' % ALTERNATE)
		client.force_login(user)

		response = client.get(reverse('auth:openid-auth-token', args=(authserver.pk,)), {
			'redirect_uri': '%s/callback' % ALTERNATE_URL, 'scope': 'openid',
			'client_id': authserver.client_id, 'response_type': 'token', 'state': 'state-token'})

		self.assertEqual(response.status_code, 302)
		self.assertTrue(response['Location'].startswith('%s/callback' % ALTERNATE_URL))
		self.assertTrue(parse_qs(urlsplit(response['Location']).query).get('access_token'))


class AdminFallbackTests(SiteSettingsMixin, TestCase):
	'''	The admin works on every allowed host, and resolving a host that has no site leaves
		nothing behind in the process-wide sites cache.
	'''
	def admin_login(self, host):
		response = self.client.get(reverse('admin:login'), HTTP_HOST=host)
		self.assertEqual(response.status_code, 200)
		return response.context['site']

	def test_admin_login_on_a_host_without_a_site(self):
		self.assertEqual(self.admin_login('alias.example.com'), self.default)

	@override_settings(LOGOUT_REDIRECT_URL=None)
	def test_admin_logout_on_a_host_without_a_site(self):
		self.client.force_login(User.objects.create_user('ada.mendes', password='x', is_staff=True))
		response = self.client.post(reverse('admin:logout'), HTTP_HOST='alias.example.com')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['site'], self.default)

	def test_fallback_hosts_do_not_accumulate_in_the_sites_cache(self):
		for index in range(25):
			host = 'fallback-%d.example.com:%d' % (index, 8000 + index)
			self.client.get(reverse('ohif-config'), HTTP_HOST=host)
			self.admin_login(host)
			# Read at assertion time: `clear_cache()` replaces the module's dictionary
			self.assertNotIn(host, sites_models.SITE_CACHE)
			self.assertNotIn(host.split(':')[0], sites_models.SITE_CACHE)

	def test_site_edits_are_seen_by_the_next_request(self):
		self.assertEqual(self.admin_login('alias.example.com'), self.default)

		created = Site.objects.create(domain='alias.example.com', name='Alias')
		self.assertEqual(self.admin_login('alias.example.com'), created)
		self.assertEqual(request_site(self.request('alias.example.com')), created)

		Site.objects.filter(pk=created.pk).update(domain='renamed.example.com')
		self.assertEqual(self.admin_login('alias.example.com'), self.default)
		self.assertEqual(self.admin_login('renamed.example.com').pk, created.pk)

		Site.objects.filter(pk=created.pk).delete()
		self.assertEqual(self.admin_login('renamed.example.com'), self.default)


class AlternateSiteLoginTests(SiteSettingsMixin, SocialLoginTestCase):
	'''	The platform login on an alternate site, from `LoginView` through the provider and back
	'''
	def setUp(self):
		super().setUp()
		self.client = Client(HTTP_HOST='%s:8070' % ALTERNATE)

	def expected_redirect_uri(self):
		return '%s%s' % (ALTERNATE_URL, self.callback_url())

	def start(self, destination):
		'''	Follow LoginView to the OpenID login and return the provider query
		'''
		response = self.client.get(reverse('login'), { 'next': destination })
		self.assertEqual(response.status_code, 302)
		response = self.client.get(response['Location'])
		self.assertEqual(response.status_code, 302)
		return { key: val[0] for key, val in parse_qs(urlsplit(response['Location']).query).items() }

	def complete(self, sent):
		self.idp.token_response['id_token'] = make_id_token(nonce=self.pending()[sent['state']]['nonce'])
		return self.callback(sent['state'])

	def test_site_destinations_are_reached(self):
		for destination in ('/viewer/?a=1', '%s/viewer/' % ALTERNATE_URL, 'http://%s:8070/viewer/' % PRIMARY,
				CALLBACK):
			self.client.logout()
			self.assertLoggedIn(self.complete(self.start(destination)), destination)

	def test_off_site_destinations_are_refused_before_the_provider(self):
		for destination in OFF_SITE:
			self.client.logout()
			response = self.client.get(reverse('login'), { 'next': destination })
			response = self.client.get(response['Location'])

			self.assertEqual(response.status_code, 403, destination)
			self.assertNotIn('Location', response)
			self.assertFalse(self.pending())

	def test_the_callback_refuses_an_off_site_destination(self):
		'''	The destination is checked again after the provider returns
		'''
		for destination in OFF_SITE:
			self.assertFalse(self.authserver.is_safe_url(destination), destination)
		for destination in ('/viewer/?a=1', '%s/viewer/' % ALTERNATE_URL, CALLBACK):
			self.assertTrue(self.authserver.is_safe_url(destination), destination)

	def test_redirect_uri_is_scoped_to_the_site_and_matches_the_exchange(self):
		for flags in ({ 'SITE_CONNECT_MATCH_SITE_NETLOC': True }, { 'SITE_CONNECT_MATCH_SITE_SCHEME': True }):
			with self.subTest(**flags), override_settings(**flags):
				self.client.logout()
				self.idp.token_requests[:] = []
				sent = self.start('/viewer/')

				self.assertEqual(sent['redirect_uri'], self.expected_redirect_uri())
				self.assertEqual(self.pending()[sent['state']]['redirect_uri'], self.expected_redirect_uri())

				self.assertLoggedIn(self.complete(sent), '/viewer/')
				self.assertEqual(self.idp.token_requests[-1].get('redirect_uri'), self.expected_redirect_uri())
