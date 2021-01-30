from ..apisettings import SONADOR_OUTPUT_TYPE_OHIF, SONADOR_OUTPUT_TYPE_QUERY_PARAM
from ..models.servers import PacsImagingServer

from .base import SonadorApiObjectMixin, SonadorApiObjectManagementView, SonadorApiRestView


class OhifApiObjectMixin(SonadorApiObjectMixin):
	'''	Mixin class that is able to toggle between a standard JSON representation of
		the PACS imaging server data and the format required by OHIF.
	'''
	def getModelJsonData(self, instance, request, vargs=None, vkwargs=None):
		'''	Convert model instance to JSON (dictionary). For GET requests where an OHIF representation is requested,
			provide the model's  `ohif_json` property (if available).
		'''
		# Provide OHIF JSON output for object
		if instance and request.method == 'GET' \
			and SONADOR_OUTPUT_TYPE_OHIF in request.GET.get(SONADOR_OUTPUT_TYPE_QUERY_PARAM, []) \
			and hasattr(instance, 'ohif_json'):
			return instance.ohif_json

		return super(OhifApiObjectMixin, self).getModelJsonData(
			instance, request, vargs=None, vkwargs=None)


class PacsImagingServerApiManagementView(OhifApiObjectMixin, SonadorApiObjectManagementView):
	'''	API object management view for PACS Imaging servers managed by Sonador.
	'''
	model = PacsImagingServer


class PacsImagingServerApiRestView(OhifApiObjectMixin, SonadorApiRestView):
	'''	API REST view for PACS Imaging servers managed by Sonador.
	'''
	model = PacsImagingServer
	