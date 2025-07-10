from ..models.userpref import UserPref
from ..forms.userpref import UserPrefForm
import json

from guru.views import GuruApiDetailsMixin, GuruApiCreateView


class UserPrefApiManagementView(GuruApiDetailsMixin, GuruApiCreateView):
	'''	API REST view for User Prefs managed by Sonador.
	'''
	model = UserPref
	modelform = UserPrefForm

	def getObject(self, request, *args, objectid=None, **kwargs):
		model,created =  self.model.objects.get_or_create(user=self.request.user)
		return model

	def get(self, request, *args, **kwargs):
		return super().get(request, *args, objectid=None, **kwargs)