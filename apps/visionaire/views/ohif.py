from django.shortcuts import reverse
from django.db.models import Q
from django.views.generic.base import TemplateView
from django.http import Http404
from django.templatetags.static import static

from django.contrib.sites.shortcuts import get_current_site

from guru.helpers import gsetting, site_fullurl
from guru.errors import ConfigurationError

from wgtauth.apisettings import OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE

from ..auth.models import SocialAuthorizationServer, SocialUserAccount
from ..auth.views.base import get_default_authserver, OpenIDAuthServerMixin
from ..models import PacsImagingServer
from ..models.branding import SonadorSite

from .base import SONADOR_OHIF_CLIENTID, SONADOR_OHIF_SITE, SONADOR_OHIF_APP, SONADOR_CONFIG_SUPPORTED


class OhifConfigView(OpenIDAuthServerMixin, TemplateView):
	'''	View used to dynamically render OHIF application JavaScript file
	'''

	template_name = 'ohif/sonador.app-config.json'
	authserver_objectid_url_param = 'serverid'
	imageserver_objectid_url_param = 'iserverid'
	model = PacsImagingServer

	def get_context_data(self, **kwargs):
		'''	OHIF viewer settings and components
		'''
		context = super(OhifConfigView, self).get_context_data(**kwargs)

		# Retrieve currently active site and any associated custom branding
		site = get_current_site(self.request)
		ssite = SonadorSite.objects.filter(pk=site.pk).first()

		# Add logo image.
		#
		# Branding URLs are consumed by a viewer that is NOT necessarily served from this origin --
		# a standalone/PWA build fetches this config cross-origin and resolves any relative URL
		# against its own host, where /static/... does not exist. Uploaded logos come back from the
		# media storage already fully qualified, which is why the configured case has always
		# worked; the static fallbacks are relative, so they are absolutised here.
		#
		# ONLY the static fallbacks. site_fullurl rewrites the netloc of any URL whose hostname
		# matches the site's (see its match_site_netloc branch), so passing an uploaded media URL
		# through it would rewrite a media host that differs from the site only by port -- exactly
		# how object storage is deployed here -- and break a URL that works today.
		context['site'] = ssite if ssite else site
		if ssite and ssite.logo:
			context['logo'] = ssite.logo.url
		else:
			context['logo'] = site_fullurl(static('images/sonador-logo.ng.svg'), request=self.request)

		# Add narrow (square) mark, shown when the viewer's studylist sidebar is collapsed
		if ssite and ssite.logo_narrow:
			context['logo_narrow'] = ssite.logo_narrow.url
		else:
			context['logo_narrow'] = site_fullurl(static('images/sonador-mark.svg'), request=self.request)

		# Add welcome message
		if ssite and ssite.welcome:
			context['empty_state'] = ssite.welcome
		else: context['empty_state'] = gsetting('VIEWER_EMPTY_STATE_MESSAGE')

		# Add farewell message, shown by the viewer's sign-out confirmation page
		if ssite and ssite.farewell:
			context['farewell'] = ssite.farewell
		else: context['farewell'] = gsetting('VIEWER_FAREWELL_MESSAGE')

		# Post logout destination, emitted root relative on purpose. The viewer resolves it against
		# its own origin (never its `routerBasename`, which is server specific), so each deployment
		# lands on the sign-out page it actually serves: Sonador for the integrated viewer, and its
		# own host for a standalone/PWA build. A fully qualified Sonador URL here would drag a
		# standalone viewer off its origin on logout.
		context['post_logout_redirect_url'] = reverse('logout-redirect')

		# End session endpoint, used by the viewer's logout fallback. Fully qualified because it is
		# always Sonador that owns the session, whatever origin the viewer is served from.
		context['end_session_url'] = site_fullurl(reverse('logout'))

		# If enabled, add the authentication endpoint
		if gsetting('AUTH_ENABLED'):

			# Retrieve OHIF configuration type (site or app)
			ohif_configtype = self.request.GET.get('type', SONADOR_OHIF_SITE)
			if not ohif_configtype in SONADOR_CONFIG_SUPPORTED:
				raise ValueError('Unsupported OHIF configuration: %s' % ohif_configtype)

			# oAuth configuration for specific server requested
			if self.kwargs.get(self.authserver_objectid_url_param):
				authserver = self.get_auth_server(self.request, self.args, self.kwargs)
				authserver_id = authserver.pk

			# oAuth configuration for default server requested
			else:
				authserver = get_default_authserver(authserver_model=self.authserver_model)
				authserver_id = None

			if not authserver:
				ConfigurationError('Sonador requires that at least one OpenID connect server '
					+ 'be configured in order to run with authentication enabled.')

			# Authentication configuration
			context['authserver'] = authserver
			context['oauth_endpoint'] = site_fullurl(authserver.url_token if authserver_id else reverse('auth:openid-auth-token-default'))
			context['oauth_clientid'] = authserver.client_id if authserver else 'sonador'
			context['oauth_response_type'] = OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE if ohif_configtype == SONADOR_OHIF_APP \
				else OAUTH_TOKEN_RESPONSE_TYPE

		# Retrieve configuration for a specific image server
		if self.kwargs.get(self.imageserver_objectid_url_param):
			try:
				iserver = self.model.objects.get(pk=self.kwargs.get(self.imageserver_objectid_url_param))
				context['router_base'] = iserver.url_viewer+'/'
			except self.model.DoesNotExist as err:
				raise Http404('Imaging server %s does not exist' % self.kwargs.get(self.imageserver_objectid_url_param))
		else:
			context['router_base'] = '/'

		# Sonador root URL
		context['SONADOR_URL'] = site_fullurl(request=self.request)

		# Version of the Sonador web application serving this configuration. Emitted alongside the
		# branding and connection settings so the viewer can report, in its About table, which
		# Sonador API build the frontend is talking to. Deployments are frequently mixed (a viewer
		# bundle and a web application released on separate cadences), so the two versions have to
		# be reported independently.
		context['SONADOR_VERSION'] = gsetting('SONADOR_VERSION')

		return context


class OhifDicomViewer(TemplateView):
	'''	Sonador OHIF Dicom Viewer. This viewer is provided as a set of script tags
		and must be compiled using `gulp.js` before it will be available.
	'''
	template_name = 'base.html'
	imageserver_objectid_url_param = 'iserverid'
	model = PacsImagingServer

	def get_context_data(self, *args, **kwargs):
		context = super(OhifDicomViewer, self).get_context_data(*args, **kwargs)

		# Retrieve currently active site and any associated custom branding
		site = get_current_site(self.request)
		ssite = SonadorSite.objects.filter(pk=site.pk).first()
		# See OhifConfigView.get_context_data on why the static fallbacks are absolutised.
		context['site'] = ssite if ssite else site
		if ssite and ssite.logo:
			context['logo'] = ssite.logo.url
		else:
			context['logo'] = site_fullurl(static('images/sonador-logo.ng.svg'), request=self.request)

		# Narrow (square) mark, shown when the viewer's studylist sidebar is collapsed
		if ssite and ssite.logo_narrow:
			context['logo_narrow'] = ssite.logo_narrow.url
		else:
			context['logo_narrow'] = site_fullurl(static('images/sonador-mark.svg'), request=self.request)

		# Empty state (first-run) messageo
		if ssite and ssite.welcome:
			context['empty_state'] = ssite.welcome
		else: context['empty_state'] = gsetting('VIEWER_EMPTY_STATE_MESSAGE')

		# Farewell message shown by the viewer's sign-out confirmation page
		if ssite and ssite.farewell:
			context['farewell'] = ssite.farewell
		else: context['farewell'] = gsetting('VIEWER_FAREWELL_MESSAGE')

		# Retrieve configuration for a specific image server
		if self.kwargs.get(self.imageserver_objectid_url_param):
			try:
				iserver = self.model.objects.get(pk=self.kwargs.get(self.imageserver_objectid_url_param))
				context['pacs_server'] = [iserver.ohif_json]
				context['pacs_config'] = iserver.url_viewer_config
			except self.model.DoesNotExist as err:
				raise Http404('Imaging server %s does not exist' % self.kwargs.get(self.imageserver_objectid_url_param))
		else:

			def ohif_json(s):
				'''	Retrieve OHIF configuration and permissions
				'''
				# Retrieve server configuration
				sjson = s.ohif_json

				# Add permissions for user
				if getattr(self, 'request', None) and getattr(self.request, 'user', None):
					sjson['perms'] = s.server_perms(self.request.user)

				return sjson

			context['pacs_server'] = [ohif_json(s) for s in self.get_imaging_servers(*args, **kwargs)]
			context['pacs_config'] = reverse('ohif-config')

		# Sonador root URL
		context['SONADOR_URL'] = site_fullurl(request=self.request)

		return context

	def get_imaging_servers(self, *args, **kwargs):
		'''	Retrieve the imaging server list for the viewer
		'''
		if getattr(getattr(self, 'request', None), 'user', None):

			# For administrative users, return all active servers
			if self.request.user and self.request.user.is_superuser:
				return self.model.objects.filter(active=True)

			# Retrieve servers for which a specific user is authorized
			return self.model.objects.filter(active=True).filter(
				Q(user_authorizations__user=self.request.user) | Q(group_authorizations__group__user=self.request.user)).distinct()

		return self.model.objects.none()


class OhifSignedOutViewer(OhifDicomViewer):
	'''	Viewer shell served at the OpenID `post_logout_redirect_uri`, where the viewer renders its
		sign-out confirmation page.

		Unlike every other viewer route this one is deliberately *not* wrapped in `login_required`.
		The user arrives here with their session already destroyed, so requiring a login would send
		them straight back through the OpenID workflow and silently sign them back in -- the
		"logout does nothing" loop reported in ohif-viewers#31.

		No imaging servers are exposed: the request is anonymous by definition, and the inherited
		authorization query cannot be evaluated against an unauthenticated user.
	'''

	def get_imaging_servers(self, *args, **kwargs):
		return self.model.objects.none()
