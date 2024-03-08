from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from ...views.base import SonadorApiObjectManagementView, SonadorApiRestView
from ..forms import UserCreationForm, UserChangeForm, GroupForm



class UserApiMixin:
	'''	Mixin class which provides methods for working with user models and for obfuscating
		sensitive fields.
	'''

	def getModelJsonData(self, instance, request, vargs=None, vkwargs=None):
		'''	Retrieve user details, remove hashed password and other sensitive information
			from response.
		'''
		json = super().getModelJsonData(self, instance, vargs=vargs, vkwarg=vkwargs)
		json.pop('password', None)	
		return json	


class UserManagementView(UserApiMixin, SonadorApiObjectManagementView):
	'''	Sonador user API management view: create new users, list/filter existing users
	'''
	model = get_user_model()
	modelform = UserCreationForm


class UserRestView(UserApiMixin, SonadorApiRestView):
	''' View to manage user instances
	'''
	model = get_user_model()
	modelform = UserChangeForm


class GroupManagementView(SonadorApiObjectManagementView):
	'''	Sonador group API management view: create new users, list/filter existing users
	'''
	model = Group
	modelform = GroupForm

	
class GroupRestView(SonadorApiRestView):
	'''	View to manage groups
	'''
	model = Group
	modelform = GroupForm
