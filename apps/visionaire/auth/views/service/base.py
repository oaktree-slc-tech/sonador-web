import logging, six, copy, base64
from six.moves.urllib import parse as urlparse

from ....views import JSONFormApiView

logger = logging.getLogger(__name__)


class SonadorServiceAuthorizationBaseView(JSONFormApiView):
	''' Form instance which can be used to process authorization requests sent from 
		services integrated with Sonador.
	'''
	formclass = None

	def getRequestJsonData(self, *args, **kwargs):
		'''	Retrieve the JSON data from the request
		'''
		data = super(SonadorServiceAuthorizationBaseView, self).getRequestJsonData(*args, **kwargs)

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

	