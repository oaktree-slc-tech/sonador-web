import json

from django import forms
from django.forms.models import model_to_dict

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from core.search import SonadorUnifiedSearchForm, SonadorUnifiedSearchView

from guru.errors import ConfigurationError
from guru.helpers.user import user_displayname
from guru.filter.forms import GuruFilterForm
from guru.filter.views import GuruQueryParamFilterFormMixin, GuruFilterView
from guru.helpers.compatability import guru_page_not_found

from ...views.base import SonadorApiObjectManagementView, SonadorApiRestView
from ..models.user import SonadorProxyUser, SonadorProxyGroup
from ..forms import UserCreationForm, UserChangeForm, GroupForm

from .service.base import OrthancServiceImagingServerMixin



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


class PacsImagingServerFrontendUserFilterForm(UserFilterBaseForm):
	'''	Filter form instance used by frontend API views for search/filter of Sonador users
	'''
	filtermodel = get_user_model()

	filterkey_transforms = {		
		'first_name': 'first_name__icontains',
		'last_name': 'last_name__icontains',
		'email': 'email__icontains',
	}

	def __init__(self, *args, server=None, **kwargs):
		self.server = server
		if not server:
			raise ValueError('Unable to initialize user filter form, invalid imaging server instance')

		super().__init__(*args, **kwargs)

	def getObjectManager(self):
		'''	Filter user list to only those which have access to ther server 
		'''
		return super().getObjectManager().filter(groups__server_authorizations__server=self.server).distinct()


class PacsImagingServerUserFilterView(OrthancServiceImagingServerMixin, UserApiMixin, GuruFilterView):
	'''	Sonador API view which can be used to search/filter Sonador users
	'''
	filterform = PacsImagingServerFrontendUserFilterForm

	def getFilterFormParams(self, request=None, vargs=None, vkwargs=None):
		'''	Add imaging server reference to filter form parameters
		'''
		fparams = super().getFilterFormParams(request=request, vargs=vargs, vkwargs=vkwargs)
		fparams['server'] = self.getImagingServer()		

		return fparams


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


class PacsImagingServerFrontendGroupFilterForm(GroupFilterBaseForm):
	'''	Filter form instance used by frontend API views for search/filter of Sonador groups
	'''
	filtermodel = Group

	filterkey_transforms = {
		'name': 'name__icontains'
	}

	def __init__(self, *args, server=None, **kwargs):
		self.server = server
		if not server:
			raise ValueError('Unable to initialize group filter form, invalid imaging server instance')
			
		super().__init__(*args, **kwargs)

	def getObjectManager(self):
		'''	Filter user list to only those which have access to ther server 
		'''
		return super().getObjectManager().filter(server_authorizations__server=self.server).distinct()


class PacsImagingServerGroupFilterView(OrthancServiceImagingServerMixin, GuruFilterView):
	'''	Sonador API view which can be used to search/filter Sonador groups
	'''
	filterform = PacsImagingServerFrontendGroupFilterForm

	def getFilterFormParams(self, request=None, vargs=None, vkwargs=None):
		'''	Add imaging server reference to filter form parameters
		'''
		fparams = super().getFilterFormParams(request=request, vargs=vargs, vkwargs=vkwargs)
		fparams['server'] = self.getImagingServer()

		return fparams


class PacsImagingUnifiedAuthModelSearchForm(SonadorUnifiedSearchForm):
	'''	Search form which can be used to execute full text searches across the user and group models.
	'''
	searchmodels = {
		'user': SonadorProxyUser, 'group': SonadorProxyGroup,
	}
	searchmodel_filter_fieldmap = {
		'user': ('username', 'email', 'first_name', 'last_name'),
		'group': ('name',)
	}

	# User filter fields
	username = forms.CharField(max_length=256, required=False)
	first_name = forms.CharField(max_length=512, required=False)
	last_name = forms.CharField(max_length=512, required=False)
	email = forms.CharField(max_length=2048, required=False)

	# Group filter fields
	name = forms.CharField(max_length=256, required=False)

	# Filter key transforms for the search form {model}.{field}
	filterkey_transforms = {
		'user.username': 'username__icontains',
		'user.email': 'email__icontains',
		'user.first_name': 'first_name__icontains',
		'user.last_name': 'last_name__icontains',
		'group.name': 'name__icontains',
	}

	def __init__(self, *args, server=None, **kwargs):
		self.server = server
		super().__init__(*args, **kwargs)

		if not self.server:
			raise ConfigurationError('Unable to initialize unified auth form, no imaging server provided')

	def _get_filter_params(self, mlabel):
		fparams = super()._get_filter_params(mlabel)

		# Add imaging server to the query filter parameters
		if mlabel == 'user':
			fparams['groups__server_authorizations__server'] = self.server
		elif mlabel == 'group':
			fparams['server_authorizations__server'] = self.server

		return fparams


class PacsImagingUnifiedAuthModelSearchView(OrthancServiceImagingServerMixin, SonadorUnifiedSearchView):
	'''	Search view which can be used to execute full text search across user and group models.
	'''
	formclass = PacsImagingUnifiedAuthModelSearchForm

	def get_form_kwargs(self, *args, **kwargs):
		'''	Retrieve optional keyword arguments for the form

			@returns dict or OrderedDict
		'''
		form_kwargs = super().get_form_kwargs(*args, **kwargs)
		form_kwargs['server'] = self.getImagingServer(*args, **kwargs)

		return form_kwargs

	def post(self, request, *args, **kwargs):
		'''	Execute search requests
		'''
		try: server = self.getImagingServer(*args, **kwargs)
		except self.imagingserver_class.DoesNotExist as err:
			return guru_page_not_found(required, err)

		return super().post(request, *args, **kwargs)