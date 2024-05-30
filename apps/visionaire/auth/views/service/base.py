import logging, six, copy, base64
from six.moves.urllib import parse as urlparse

from guru.apisettings import HTTP_CONTENT_JSON, HTTP_CONTENT_FORM_ENCODED
from guru.helpers import gsetting

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


class SonadorServiceAuthorizationBaseView(JSONFormApiView):
	''' Form instance which can be used to process authorization requests sent from 
		services integrated with Sonador.
	'''
	formclass = None
	cache_validation = False

	def get_form_kwargs(self, *args, **kwargs):
		'''	Retrieve keyword arguments for the form instance.
		'''
		form_kwargs = super().get_form_kwargs(*args, **kwargs)

		# Add authorization cache setting to form
		if form_kwargs.get('cache_validation') is None:
			form_kwargs['cache_validation'] = self.cache_validation

		return form_kwargs

	def getRequestJsonData(self, *args, **kwargs):
		'''	Retrieve the data from the request. The service view is able
			to work with JSON data encoded in the body of the request of form-encoded data.
		'''
		# Parse request body to JSON
		if HTTP_CONTENT_JSON.lower() in self.request.content_type.lower():
			data = super(SonadorServiceAuthorizationBaseView, self).getRequestJsonData(*args, **kwargs)

		# Retrieve form encoded parameters
		elif HTTP_CONTENT_FORM_ENCODED.lower() in self.request.content_type.lower():
			data = self.request.POST

		# Unsupported authorization request
		else:
			raise NotImplementedError('Unable to retrieve data, invalid content type: %s' % self.request.content_type)

		# Apply formdata transforms to transform request keys to the correct form field keys
		fclass = self.get_form_class()
		if hasattr(fclass, 'formdata_transforms') and isinstance(fclass.formdata_transforms, dict):
			for k, v in six.iteritems(fclass.formdata_transforms):

				if k in data:
					fdata = data.pop(k)
					data[v] = fdata

		logger.debug('Service authorization request data:\n%r' % data)
		return data
	
	def form_valid(self, form):
		return super(SonadorServiceAuthorizationBaseView, self).form_valid(form)

	