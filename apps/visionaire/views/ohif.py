from django.shortcuts import reverse
from django.views.generic.base import TemplateView

from guru.helpers import gsetting

from .base import SONADOR_OHIF_CLIENTID

class OhifConfigView(TemplateView):
	'''	View used to dynamically render OHIF application JavaScript file
	'''

	template_name = 'ohif/sonador.app-config.js'

	def get_context_data(self, **kwargs):
		'''	OHIF viewer settings and components	
		'''
		context = super(OhifConfigView, self).get_context_data(**kwargs)

		# If enabled, add the authentication endpoint
		if gsetting('AUTH_ENABLED'):
			context['oauth_endpoint'] = reverse('auth:openid-auth-token')
			context['oauth_clientid'] = SONADOR_OHIF_CLIENTID

		return context


class OhifDicomViewer(TemplateView):
	'''	Default
	'''

	template_name = 'base.html'

	def get_context_data(self, *args, **kwargs):
		context = super(OhifDicomViewer, self).get_context_data(*args, **kwargs)
		return context
