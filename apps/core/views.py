import logging

from django.core import signing
from django.http import JsonResponse
from django.views.generic.base import TemplateView
from django.shortcuts import reverse

from guru import apisettings as gapi
from guru.views import GuruApiRequestMixin, GuruApiObjectMixin, GuruApiObjectManagementView, GuruApiRestView
from guru.views.json import JSONResponseMixin, JSONBaseView, JSONFormApiView
from guru.helpers import operation_results, gsetting
from guru.helpers.utils.object import pick
from guru.errors import OperationError

logger = logging.getLogger(__name__)


class SonadorApiObjectMixin(GuruApiObjectMixin):
	'''	Mixin class with methods for managing Sonador objects
	'''
	def getModelJsonData(self, instance, request, vargs=None, vkwargs=None):
		'''	Convert model instance to JSON (dictionary). For GET requests, use the model's 
			`json` property (if available).
		'''
		if instance and request.method == 'GET' and hasattr(instance, 'json'):
			return instance.json

		return super(SonadorApiObjectMixin, self).getModelJsonData(
			instance, request, vargs=None, vkwargs=None)


class SonadorApiObjectManagementView(SonadorApiObjectMixin, GuruApiObjectManagementView):
	'''	Sonador API object management view
	'''


class SonadorApiRestView(SonadorApiObjectMixin, GuruApiRestView):
	'''	Sonador API REST View
	'''


