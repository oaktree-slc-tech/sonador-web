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
from guru.helpers.utils.object import pick, omit
from guru.helpers.query import dict2_OR_query

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


class LookupViewFormMixin:
	'''	View mixin class which provides a get_data method that can execute lookups and will serialize
		the results to JSON.
	'''
	form_lookup_field = None

	def init_lookup_mixin(self, *args, **kwargs):
		self.form_lookup_field = kwargs.get('form_lookup_field', self.form_lookup_field)

		if not self.form_lookup_field:
			raise ConfigurationError('Unable to initialize view instance, no form lookup field defined.')

	def get_data(self, context):
		'''	Execute the form search return the results list
		'''
		response = super().get_data(context)

		# Retrieve form and serialize lookup results to JSON
		form = context.get('form') or self.get_form()
		if form.is_valid():
			response['results'] = [self.getModelJsonData(_u, self.request) for _u in form.cleaned_data.get(self.form_lookup_field, [])]

		return response



# User Management and Lookup Views

def permission2json(permission):
	'''	Convert the provided permission instance to JSON
	'''
	return pick(permission, ('id', 'name', 'codename'))


def group2json(group, json_data=None, include_group_permissions=False):
	'''	Convert the provided group instance to 
	'''
	json_data = json_data or (model_to_dict(group) if group else {})

	# Remove sensitive details from response
	if not include_group_permissions:
		json_data.pop('permissions')

	# Encode permissions to JSON
	if json_data.get('permissions'):
		_permissions = json_data.get('permissions')
		json_data['permissions'] = [permission2json(p) for p in _permissions]

	return json_data


def user2json(user, json_data=None, include_groups=False, include_permissions=False):
	'''	Create JSON response structure for the provided user instance
	'''
	json_data = json_data or (model_to_dict(user) if user else {})

	# Remove password field
	json_data.pop('password', None)

	# Convert group models to JSON
	if json_data.get('groups') and include_groups:
		json_data['groups'] = [group2json(g) for g in json_data['groups']]

	# Scrub groups and permissions from response if indicated
	if not include_groups:
		json_data.pop('groups', None)

	# Remove sensitive details from response
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

	# Convert permissions to JSON
	if json_data.get('user_permissions'):
		_permissions = json_data.get('user_permissions')
		json_data['user_permissions'] = [permission2json(p) for p in _permissions]

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
		'''	Filter user list to only those which have access to the server 
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


class SonadorUserLookupForm(forms.Form):
	'''	Form class which can be used to lookup Sonador users by ID
	'''
	users = forms.ModelMultipleChoiceField(queryset=get_user_model().objects.all())


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


class SonadorUserLookupView(UserApiMixin, LookupViewFormMixin, JSONFormApiView):
	'''	Sonador API view which can be used to lookup users by ID: lookup requests include all users on the platform.
	'''
	formclass = SonadorUserLookupForm
	form_lookup_field = 'users'
	
	# User JSON serialization options
	include_groups = True
	include_permissions = True

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.init_lookup_mixin(*args, **kwargs)


class PacsImagingServerUserLookupView(UserApiMixin, LookupViewFormMixin, PacsImagingServerFormMixin, JSONFormApiView):
	'''	Sonador API view which can be used to lookup users by ID: lookup requests are scoped to the imaging server
		retrieved by the view.
	'''
	formclass = PacsImagingServerUserLookupForm
	form_lookup_field = 'users'

	# User JSON serialization options
	include_groups = True
	include_permissions = True

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.init_lookup_mixin(*args, **kwargs)


# Group Management and Lookup Views

class GroupApiMixin:
	'''	Mixin class which provides methods for working with group models.
	'''
	include_group_permissions = False

	def getModelJsonData(self, instance, request, *args, **kwargs):
		return group2json(instance, include_group_permissions=self.include_group_permissions) if instance else {}


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
	''' Filter form for frontend API views to search and filter Sonador groups.
		
		@field worklist (Boolean/Null): filter groups by worklist permission.
	'''
	worklist = forms.NullBooleanField(required=False)
	tag = forms.NullBooleanField(required=False)

	filtermodel = Group

	filterkey_transforms = {
		'name': 'name__icontains',
		'worklist': 'server_authorizations__worklist',
		'tag': 'server_authorizations__tag',
	}
 
	def __init__(self, *args, server=None, user=None, **kwargs):
		self.server = server
		if not server:
			raise ValueError('Unable to initialize group filter form, invalid imaging server instance')

		self.user = user
		if not user:
			raise ValueError('Unable to intiialize group filter form, invalid user instance')
			
		super().__init__(*args, **kwargs)

	def getObjectManager(self):
		'''	Filter user list to only those which have access to ther server
		'''
		_groups = super().getObjectManager().filter(server_authorizations__server=self.server)

		# Filter response by group membership
		if not self.user.is_superuser:
			_groups = _groups.filter(user=self.user)

		return _groups.distinct()


class PacsImagingServerGroupFilterView(OrthancServiceImagingServerMixin, GuruFilterView):
	'''	Sonador API view which can be used to search/filter Sonador groups. Only groups which the user
		is a member of are included in the response.
	'''
	filterform = PacsImagingServerFrontendGroupFilterForm
	include_group_permissions = False

	def getFilterFormParams(self, request=None, vargs=None, vkwargs=None):
		'''	Add imaging server reference to filter form parameters
		'''
		fparams = super().getFilterFormParams(request=request, vargs=vargs, vkwargs=vkwargs)
		fparams['server'] = self.getImagingServer()
		fparams['user'] = getattr(request, 'user', None)

		return fparams

	def getModelJsonData(self, instance, request, *args, **kwargs):
		'''	Return group JSON data
		'''
		return group2json(instance, include_group_permissions=self.include_group_permissions)


class SonadorGroupLookupForm(forms.Form):
	'''	Form class which can be used to lookup Sonador groups by ID
	'''
	groups = forms.ModelMultipleChoiceField(queryset=Group.objects.all())


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


class SonadorGroupLookupView(GroupApiMixin, LookupViewFormMixin, JSONFormApiView):
	'''	Sonador API view which can be used to lookup groups by ID: lookup requests include all groups on the platform.
	'''
	formclass = SonadorGroupLookupForm
	form_lookup_field = 'groups'

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.init_lookup_mixin(*args, **kwargs)


class PacsImagingServerGroupLookupView(GroupApiMixin, LookupViewFormMixin, PacsImagingServerFormMixin, JSONFormApiView):
	'''	Sonador API view which can be used to lookup users by ID
	'''
	formclass = PacsImagingServerGroupLookupForm
	form_lookup_field = 'groups'

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.init_lookup_mixin(*args, **kwargs)


class PacsImagingServerFrontendGroupMembershipFilterForm(PacsImagingServerFrontendUserFilterForm):
	'''	Filter form instance used by frontend API views for search/filter of Sonador users which belong
		to a specific group. Inherits from PacsImagingServerFrontendUserFilterForm which filters
		based on users which are associated with the imaging server.
	'''
	def __init__(self, *args, group=None, **kwargs):
		super().__init__(*args, **kwargs)

		self.group = group
		if not group:
			raise ValueError('Unable to initialize frontend group membership lookup form, invalid gropu instance')

	def getObjectManager(self):
		'''	Filter user list to only those who belong to the provided group.
		'''
		return super().getObjectManager().filter(groups__in=[self.group]).distinct()


class PacsImagingServerGroupMembershipLookupView(PacsImagingServerUserFilterView):
	'''	Sonador API view which can be used to search/filter Sonador users which belong to a specific group
		associated with an imaging server.
	'''
	filterform = PacsImagingServerFrontendGroupMembershipFilterForm

	group_class = Group
	group_request_param = 'groupid'

	def getGroup(self, *args, **kwargs):
		'''	Retrieve the group assocaited with the request. After being retrieved from the database, subsequent
			calls retrieve a cached copy of the data
		'''
		kwargs = kwargs or self.kwargs

		# Retrieve group
		group = kwargs.get('group')
		if not group:
			group = self.group_class.objects.get(pk=kwargs.get(self.group_request_param))
			kwargs['group'] = group

		return group

	def getFilterFormParams(self, request=None, vargs=None, vkwargs=None):
		'''	Add group instance (parsed from the URL) to the search/filter form parameters
		'''
		fparams = super().getFilterFormParams(request=request, vargs=vargs, vkwargs=vkwargs)
		fparams['group'] = self.getGroup()

		return fparams


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

	# For searches that return no results, use the following fields to execute a 
	# second search using the global term and the filterkey transforms to improve
	# the initial search results.
	fallback_user_match_fields = ('username', 'first_name', 'last_name', 'email')
	fallback_group_match_fields = ('name',)

	def __init__(self, *args, server=None, user=None, **kwargs):

		# Set server and user instance
		self.server = server
		self.user = user

		# Initialize form
		super().__init__(*args, **kwargs)

		if not self.server:
			raise ConfigurationError('Unable to initialize unified auth form, no imaging server provided')

	def _get_AND_filter_params(self, mlabel, fparams=None):
		'''	Retrieve filter parameters that should be attached to queries using an AND condition.
		'''
		fparams = fparams or {}
		
		# Add imaging server to the query filter parameters
		if mlabel == 'user':
			fparams['groups__server_authorizations__server'] = self.server
		elif mlabel == 'group':
			fparams['server_authorizations__server'] = self.server

		return fparams

	def _get_filter_params(self, mlabel, merge_AND_params=True):
		'''	Default filter parameters for the provided model label.

			@input merge_AND_params (bool, default=True): toggles whether query AND parameters
				should be included in the filter dictionary. The form is able to execute
				two searches: an "AND" search that uses full-text search and relevance
				matching and an "OR" fallback search. When True, the AND criteria for 
				the model instance will be included in the results. When false, only OR criteria
				will be added to the dictionary.

			@returns dict of mapped filter parameters
		'''
		fparams = super()._get_filter_params(mlabel)
		if merge_AND_params:
			fparams = self._get_AND_filter_params(mlabel, fparams=fparams)

		return fparams

	def _fallback_match_params(self, mlabel, fparams):
		'''	Construct a fallback match query. Used to back-fill a query in-case the standard
			unified search did not return any matches. By-passes limitations in PostgreSQL
			revelance search.

			IMPORTANT: should only be used if there are not any matches from the default
			universal search.
		'''
		# Retrieve filter parameters from form data
		fparams = self._get_filter_params(mlabel, merge_AND_params=False)

		# Retrieve fallback fields
		if mlabel == 'user':
			fallback_fields = self.fallback_user_match_fields
		elif mlabel == 'group':
			fallback_fields = self.fallback_group_match_fields
		else:
			raise ValueError('Unsupported search model "%s"' % mlabel)

		for _fname in fallback_fields:

			for _fkey in fparams:

				# Back-fill the search transform with relevant matches to the search term
				if _fname in _fkey and not fparams.get(_fkey):
					fparams[_fkey] = self.cleaned_data.get('term', '')

		return fparams

	def execute_search(self, results=None):
		'''	Execute user and group search results
		'''
		search_term = self.cleaned_data.get('term', '')

		# Execute full text search across the models
		results = super().execute_search(results=results)

		# If there aren't any results returned by the results, execute a second query utilizing
		# an __icontains mapping to try and retrieve useful initial results. When executing in 
		# this mode, results should be limited to groups to which the request user user is
		# a member and users with which there is common membership in a group.
		# IMPORTANT: Super admin users are able to search across all users associated with
		# the imaging server instance.
		print('Search results', results)
		if not results and search_term:

			# Back-fill results from fallback query
			for _mlabel, _model in self.searchmodels.items():

				# Retrieve fallback results using ICONTAINS query of the database
				results.extend(
					_model.objects.filter(
							dict2_OR_query(self._fallback_match_params(_mlabel, _model)))
						.filter(**self._get_AND_filter_params(_mlabel))
						.distinct())

		return results


class PacsImagingUnifiedAuthModelSearchView(PacsImagingServerFormMixin, SonadorUnifiedSearchView):
	'''	Search view which can be used to execute full text search across user and group models.
	'''
	formclass = PacsImagingUnifiedAuthModelSearchForm
