import json

from django import forms
from django.forms.models import model_to_dict

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from guru.helpers.user import user_displayname
from guru.filter.forms import GuruFilterForm
from guru.filter.views import GuruQueryParamFilterFormMixin, GuruFilterView

from ...views.base import SonadorApiObjectManagementView, SonadorApiRestView
from ..forms import UserCreationForm, UserChangeForm, GroupForm



class UserFilterBaseForm(GuruFilterForm):
	'''	Filter form which can be used to search for user instances
	'''
	username = forms.CharField(max_length=256, required=False)
	first_name = forms.CharField(max_length=512, required=False)
	last_name = forms.CharField(max_length=512, required=False)
	email = forms.CharField(max_length=2048, required=False)


class UserApiMixin:
	'''	Mixin class which provides methods for working with user models and for obfuscating
		sensitive fields.
	'''
	include_groups = False
	include_permissions = False

	def getModelJsonData(self, instance, request, vargs=None, vkwargs=None):
		'''	Retrieve user details, remove hashed password and other sensitive information
			from response.
		'''
		json = super().getModelJsonData(instance, request, vargs=vargs, vkwargs=vkwargs)
		json.pop('password', None)

		# Convert group models to JSON
		if json.get('groups') and self.include_groups:
			json['groups'] = [g for g in map(model_to_dict, json['groups'])]

		# Scrub groups and permissions from response if indicated
		if not self.include_groups:
			json.pop('groups', None)

		# Remove sensitive details from resonse
		if not self.include_permissions:
			json.pop('user_permissions', None)
			json.pop('is_active', None)
			json.pop('is_staff', None)
			json.pop('is_superuser', None)
			json.pop('date_joined', None)
			json.pop('last_login', None)

		# Add user name to JSON
		if instance:
			json['name'] = user_displayname(instance)

		return json


class UserManagementView(GuruQueryParamFilterFormMixin, UserApiMixin, SonadorApiObjectManagementView):
	'''	Sonador user API management view: create new users, list/filter existing users
	'''
	model = get_user_model()
	modelform = UserCreationForm
	filterform = UserFilterBaseForm

	def __init__(self, *args, **kwargs):
		self.initFilterForm()
		super().__init__(*args, **kwargs)


class UserRestView(UserApiMixin, SonadorApiRestView):
	''' View to manage user instances
	'''
	model = get_user_model()
	modelform = UserChangeForm


class FrontendUserFilterForm(UserFilterBaseForm):
	'''	Filter form instance used by frontend API views for search/filter of Sonador users
	'''
	filtermodel = get_user_model()

	filterkey_transforms = {
		'first_name': 'first_name__icontains',
		'last_name': 'last_name__icontains',
		'email': 'email__icontains',
	}


class UserFilterView(UserApiMixin, GuruFilterView):
	'''	Sonador API view which can be used to search/filter Sonador users
	'''
	filterform = FrontendUserFilterForm


class GroupFilterBaseForm(GuruFilterForm):
	'''	Filter form which can be used to search for group instances
	'''
	name = forms.CharField(max_length=256, required=False)


class GroupManagementView(GuruQueryParamFilterFormMixin, SonadorApiObjectManagementView):
	'''	Sonador group API management view: create new users, list/filter existing users
	'''
	model = Group
	modelform = GroupForm
	filterform = GroupFilterBaseForm

	def __init__(self, *args, **kwargs):
		self.initFilterForm()
		super().__init__(*args, **kwargs)


class GroupRestView(SonadorApiRestView):
	'''	View to manage groups
	'''
	model = Group
	modelform = GroupForm


class FrontendGroupFilterForm(GroupFilterBaseForm):
	'''	Filter form instance used by frontend API views for search/filter of Sonador groups
	'''
	filtermodel = Group

	filterkey_transforms = {
		'name': 'name__icontains'
	}
	

class GroupFilterView(GuruFilterView):
	'''	Sonador API view which can be used to search/filter Sonador groups
	'''
	filterform = FrontendGroupFilterForm

