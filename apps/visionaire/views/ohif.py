from django.shortcuts import reverse
from django.views.generic.base import TemplateView
from django.http import Http404

from guru.helpers import gsetting, site_fullurl
from guru.errors import ConfigurationError

from wgtauth.apisettings import OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE

from ..auth.models import SocialAuthorizationServer, SocialUserAccount
from ..auth.views.base import get_default_authserver, OpenIDAuthServerMixin
from ..models import PacsImagingServer

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
			context['oauth_clientid'] = authserver.client_id
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

		# Retrieve configuration for a specific image server
		if self.kwargs.get(self.imageserver_objectid_url_param):
			try:
				iserver = self.model.objects.get(pk=self.kwargs.get(self.imageserver_objectid_url_param))
				context['pacs_server'] = [iserver.ohif_json]
				context['pacs_config'] = iserver.url_viewer_config
			except self.model.DoesNotExist as err:
				raise Http404('Imaging server %s does not exist' % self.kwargs.get(self.imageserver_objectid_url_param))			
		else:
			context['pacs_server'] = [s.ohif_json for s in self.model.objects.filter(active=True)]
			context['pacs_config'] = reverse('ohif-config')

		return context
