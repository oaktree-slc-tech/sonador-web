from django.db.models import Q

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

	def getQueryset(self, *args, **kwargs):
		'''	Retrieve the list of servers to which the user has access. For administrative
			users, retrieve all imaging servers registered with Sonador. For non-admin users
			only include servers to which they have been granted a user or group based authorization.
		'''
		# Base queryset
		queryset = super(PacsImagingServerApiManagementView, self).getQueryset(*args, **kwargs)
		if getattr(getattr(self, 'request', None), 'user', None):

			# For administrative users, return all active servers
			if self.request.user and (self.request.user.is_superuser or self.request.user.is_staff):
				return queryset
			
			# Retrieve servers for which a specific user is authorized
			return self.model.objects.filter(active=True).filter(
				Q(user_authorizations__user=self.request.user) | Q(group_authorizations__group__user=self.request.user))

		# For unauthenticated users, return an empty queryset
		return queryset.none()


class PacsImagingServerApiRestView(OhifApiObjectMixin, SonadorApiRestView):
	'''	API REST view for PACS Imaging servers managed by Sonador.
	'''
	model = PacsImagingServer
	