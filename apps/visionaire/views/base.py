from django.core import signing
from django.http import JsonResponse
from django.views.generic.base import TemplateView
from django.shortcuts import reverse

from guru.views import GuruApiRequestMixin, GuruApiObjectMixin, GuruApiObjectManagementView, GuruApiRestView
from guru.helpers import operation_results, gsetting
from guru.helpers.utils.object import pick
from guru.errors import OperationError

from ..helpers import SESSION_SALT
from ..apisettings import SONADOR_OHIF_CLIENTID, SONADOR_OHIF_SITE, SONADOR_OHIF_APP, SONADOR_CONFIG_SUPPORTED



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


class JSONResponseMixin:
	""" A mixin that can be used to render a JSON response.
	"""
	def render_to_json_response(self, context, **response_kwargs):
		"""
		Returns a JSON response, transforming 'context' to make the payload.
		"""
		return operation_results(self.get_data(context), 
			pick(response_kwargs, ('status', 'operation', 'badrequest', 'content_type')))

	def get_data(self, context):
		"""
		Returns an object that will be serialized as JSON by json.dumps().
		"""
		return {}


class JSONBaseView(JSONResponseMixin, TemplateView):
	'''	Base view which can be used to return a JSON response.
	'''
	def render_to_response(self, context, **response_kwargs):
		return self.render_to_json_response(context, **response_kwargs)


class JSONFormApiView(GuruApiRequestMixin, JSONBaseView):
	'''	View used to process JSON
	'''
	formclass = None

	def get_form_class(self, *args, **kwargs):
		fclass = getattr(self, 'formclass', None)
		if not fclass:
			raise OperationError('No form class provided', http_code=500)

		return fclass

	def get_form_kwargs(self, *args, **kwargs):
		'''	Retrieve optional keyword arguments for the form

			@returns dict or OrderedDict
		'''
		return {}

	def get_form(self):
		'''	Retrieve form instance for the view
		'''
		if not getattr(self, 'form', None):
			setattr(self, 'form', self.get_form_class()(
				self.getRequestJsonData(self.request, vargs=self.args, vkwargs=self.kwargs),
				**self.get_form_kwargs()))

		return self.form

	def get_context_data(self, **kwargs):
		"""Insert the form into the context dict."""
		if 'form' not in kwargs:
			kwargs['form'] = self.get_form()
		
		return super(JSONFormApiView, self).get_context_data(**kwargs)

	def form_valid(self, form):
		return self.render_to_response(self.get_context_data(form=form))

	def form_invalid(self, form):		
		return self.render_to_response(self.get_context_data(form=form), badrequest=True)

	def get(self, request, *args, **kwargs):
		return self.http_method_not_allowed(request, *args, **kwargs)

	def post(self, request, *args, **kwargs):
		'''	Handle API POST requests:

			1. Instantiate a form instance with passed form body
			2. Check that it is valid, return an appropriate response
		'''
		form = self.get_form()

		if form.is_valid():
			return self.form_valid(form)

		return self.form_invalid(form)
