import logging

from django.urls import path, re_path

from guru.helpers import str2bool
from guru.filter.views import GuruQueryParamFilterFormMixin

from visionaire.views.base import SonadorApiObjectMixin, SonadorApiObjectManagementView, SonadorApiRestView

from .helpers import API_ALL_DEVICES_QSPARAM, API_ENV_INCLUDE_QSPARAM, API_ENV_ALL_KEYS_QSPARAM
from .models import ClinicalGateway
from .forms import ClinicalGatewayForm, GatewayDeviceFilterForm

logger = logging.getLogger(__name__)


class ClinicalGatewayObjectMixin(SonadorApiObjectMixin):
	'''	Mixin class that can be used to expand attributes returned by Device Gateway API endpoints.
	'''
	def getModelJsonData(self, instance, request, vargs=None, vkwargs=None):
		'''	For GET requests, additional data parameters can be toggled on/off.

			@qsparam env (bool, default=False): toggles environment variables on/off
			@qsparam env-all-keys (bool, default=False): when True, all keys (including those which are inactive) 
				will be included in the response.

		'''
		sjson = super().getModelJsonData(instance, request, vargs=vargs, vkwargs=vkwargs)

		# Add additional components to response
		if instance and request.method == 'GET':

			# Include environment variables in response
			if str2bool(request.GET.get(API_ENV_INCLUDE_QSPARAM)):
				sjson['env'] = instance.json_env(all_keys=str2bool(request.GET.get(API_ENV_ALL_KEYS_QSPARAM)))

		return sjson


class ClinicalGatewayApiManagementView(
		ClinicalGatewayObjectMixin, GuruQueryParamFilterFormMixin, SonadorApiObjectManagementView):
	'''	API object view for managing Sonador Clinical Gateway instances
	'''
	model = ClinicalGateway
	modelform = ClinicalGatewayForm
	filterform = GatewayDeviceFilterForm

	def getFilterFormParams(self, *args, **kwargs):
		fparams = super().getFilterFormParams(*args, **kwargs)

		# Ensure that a filter model has been provided to the form
		if not fparams.get('filtermodel'):
			fparams['filtermodel'] = self.model

		return fparams

	def getQueryset(self, *args, **kwargs):
		'''	Retrieve the list of devices to which the user has access. For administrative users,
			a query parameter can be passed to retrieve all devices.
		'''
		# Base queryset
		queryset = super().getQueryset(*args, **kwargs)

		# Return all devices or devices filtered by a specific user
		if self.request.user.is_superuser \
			and (str2bool(self.request.GET.get(API_ALL_DEVICES_QSPARAM)) or self.request.GET.get('user')):
			return queryset		

		# Filter devices by user
		elif self.request.user.is_authenticated:
			queryset = queryset.filter(user=self.request.user)

			# Unless an "active" flag is passed in the query string, only include active devices in the response
			if self.request.GET.get('active') is None:
				return queryset.filter(active=True)

			# Return un-filtered queryset to be further refined by the query form
			return queryset


		# Return empty queryset to prevent data leakage
		return queryset.none()

	def saveObjectData(self, request, forminstance, vargs=None, vkwargs=None):
		'''	Save the object data via the form instance and attach request user as device owner.
		'''
		setattr(forminstance.instance, 'user', self.request.user)
		return super().saveObjectData(request, forminstance, vargs=vargs, vkwargs=vkwargs)


class ClinicalGatewayApiRestView(ClinicalGatewayObjectMixin, SonadorApiRestView):
	'''	API REST view for Sonador Clnical Gateway instances
	'''
	model = ClinicalGateway
	modelform = ClinicalGatewayForm
