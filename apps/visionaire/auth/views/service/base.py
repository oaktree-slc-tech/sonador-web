import logging, six, copy, base64
from six.moves.urllib import parse as urlparse

from guru.apisettings import HTTP_CONTENT_JSON, HTTP_CONTENT_FORM_ENCODED
from guru.helpers import gsetting

from wgtauth.services.views.base import DataServiceAuthorizationBaseView

from ....views import JSONFormApiView

from ....models import PacsImagingServer

logger = logging.getLogger(__name__)


class OrthancServiceImagingServerMixin:
	'''	Mixin class used for retrieving image server instances
	'''
	imagingserver_class = PacsImagingServer
	imagingserver_request_param = 'serverid'

	def getImagingServer(self, *args, **kwargs):
		''' Retrieve the imaging server associated with the request. After being retrieved
			from the database, subsequent calls retrieve a cached copy of the data.
		'''
		kwargs = kwargs or self.kwargs

		# Retrieve imaging server
		iserver = kwargs.get('server')
		if not iserver:
			iserver = self.imagingserver_class.objects.get(
				pk=kwargs.get(self.imagingserver_request_param))
			kwargs['server'] = iserver
		
		return iserver


class SonadorServiceAuthorizationBaseView(DataServiceAuthorizationBaseView):
	''' Form instance which can be used to process authorization requests sent from 
		services integrated with Sonador.
	'''
	