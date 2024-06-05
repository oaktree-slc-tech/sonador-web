import json, logging

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

from core.views import JSONFormApiView

from ...views.base import SonadorApiObjectManagementView, SonadorApiRestView
from ..models.user import SonadorProxyUser, SonadorProxyGroup
from ..forms import UserCreationForm, UserChangeForm, GroupForm

from .service.base import OrthancServiceImagingServerMixin

logger = logging.getLogger(__name__)



# Shared Auth API Components


class PacsImagingServerFormMixin(OrthancServiceImagingServerMixin):
	'''	Mixin instance that provides methods and properties for processing API requests associated
		with an imaging server instance.
	'''
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



# User Management and Lookup Views


def user2json(user, json_data=None, include_groups=False, include_permissions=False):
	'''	Create JSON response structure for the provided user instance
	'''
	json_data = json_data or (model_to_dict(user) if user else {})

	# Remove password field
	json_data.pop('password', None)

	# Convert group models to JSON
	if json_data.get('groups') and include_groups:
		json_data['groups'] = [g for g in map(model_to_dict, json_data['groups'])]

	# Scrub groups and permissions from response if indicated
	if not include_groups:
		json_data.pop('groups', None)

	# Remove sensitive details from resonse
	if not include_permissions:
		json_data.pop('user_permissions', None)
		json_data.pop('is_active', None)
		json_data.pop('is_staff', None)
		json_data.pop('is_superuser', None)
		json_data.pop('date_joined', None)
		json_data.pop('last_login', None)

	# Add user name to JSON
	if user:
		json_data['name'] = user_displayname(user)

	return json_data


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
		try: json_data = super().getModelJsonData(instance, request, vargs=vargs, vkwargs=vkwargs)
		except AttributeError as err:
			logger.debug(('View instance does not include a getModelJsonData method. '
				+ 'An empty JSON array will be passed to user2data. Error: "%s"') % err)
			json_data = None

		return user2json(instance, json_data=json_data,
			include_groups=self.include_groups, include_permissions=self.include_permissions)


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


class PacsImagingServerUserLookupForm(forms.Form):
	'''	Form class which can be used to lookup users by ID
	'''
	users = forms.ModelMultipleChoiceField(queryset=None)

	def __init__(self, *args, server=None, **kwargs):
		'''	Initialize form instance
		'''
		self.server = server
		super().__init__(*args, **kwargs)

		if not self.server:
			raise ConfigurationError('Unable to initialize form instance, invalid imaging server instance')

		self.fields['users'].queryset = get_user_model().objects.filter(groups__server_authorizations__server=self.server)


class PacsImagingServerUserLookupView(UserApiMixin, PacsImagingServerFormMixin, JSONFormApiView):
	'''	Sonador API view which can be used to lookup users by ID
	'''
	formclass = PacsImagingServerUserLookupForm
	include_groups = True
	include_permissions = True

	def get_data(self, context):
		'''	Execute the form search return the results list
		'''
		response = super().get_data(context)

		# Retrieve form and serialize lookup results to JSON
		form = context.get('form') or self.get_form()
		if form.is_valid():
			response['results'] = [self.getModelJsonData(_u, self.request) for _u in form.cleaned_data.get('users', [])]

		logger.critical('User lookup response:\n%s' % response)
		return response


# Group Management and Lookup Views


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


class PacsImagingServerGroupLookupForm(forms.Form):
	'''	Form class which can be used to lookup users by ID
	'''
	groups = forms.ModelMultipleChoiceField(queryset=None)

	def __init__(self, *args, server=None, **kwargs):
		'''	Initialize form instance
		'''
		self.server = server
		super().__init__(*args, **kwargs)

		if not self.server:
			raise ConfigurationError('Unable to initialize form instance, invalid imaging server instance')

		self.fields['groups'].queryset = SonadorProxyGroup.objects.filter(server_authorizations__server=self.server)


class PacsImagingServerGroupLookupView(PacsImagingServerFormMixin, JSONFormApiView):
	'''	Sonador API view which can be used to lookup users by ID
	'''
	formclass = PacsImagingServerGroupLookupForm

	def getModelJsonData(self, instance, request, *args, **kwargs):
		return model_to_dict(instance) if instance else {}

	def get_data(self, context):
		'''	Execute the form search return the results list
		'''
		response = super().get_data(context)

		# Retrieve form and serialize lookup results to JSON
		form = context.get('form') or self.get_form()
		if form.is_valid():
			response['results'] = [self.getModelJsonData(_g, self.request) for _g in form.cleaned_data.get('groups', [])]

		logger.critical('Group lookup response:\n%s' % response)
		return response


# Auth Model Unified Search

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


class PacsImagingUnifiedAuthModelSearchView(PacsImagingServerFormMixin, SonadorUnifiedSearchView):
	'''	Search view which can be used to execute full text search across user and group models.
	'''
	formclass = PacsImagingUnifiedAuthModelSearchForm
