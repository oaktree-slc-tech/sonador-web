import logging, copy, base64, json

from functools import wraps

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q, Subquery
from django.apps import apps
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt, csrf_protect, requires_csrf_token
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.contrib import auth

from guru import apisettings as gapi
from guru.apisettings import HTTP_GET
from guru.helpers import create_token
from guru.helpers.compatability import guru_page_not_found

from secure import apisettings as secureapi
from secure.models import ApiAccess, ApiAccessToken

from wgtauth.apisettings import BASIC_AUTH_TYPE

from orthancapi import apisettings as orthanc_api

from ..models.servers import PacsImagingServer
from ..helpers import SESSION_SALT
from . import hexsigning

logger = logging.getLogger(__name__)


def create_session_token(session_key, token_payload=None, salt=SESSION_SALT):
	'''	Create a session token from the provided session key and token payload.

		@input session_key (str): Session key to be used for the token payload
		@input token_payload (dict): key/value data to add to the token payload

		@returns str: token value
	'''
	if token_payload and not isinstance(token_payload, dict):
		raise TypeError('Invalid type "%s", token payloads must be a dictionary instance' % type(token_payload).__name__)

	# Add token payload to dictionary
	if token_payload:
		token_payload['session'] = session_key

	return 'h:%s' % hexsigning.dumps(token_payload or session_key, salt=salt)


def parse_resource_policy(resource_pollicy, sep_policy=' ', sep_resource=',', sep_equals='='):
	'''	Parse the provided resource policy to a dictionary with study, series, and patient grants

		@returns dict
	'''
	policy = {}

	for _component in (resource_pollicy or '').split(sep_policy):

		# Split policy components to resource class and grants
		if '=' in _component:
			_rclass,_rgrant = _component.split(sep_equals)
			_rgrant = set(_rgrant.split(sep_resource))

			if _rclass in orthanc_api.IMAGING_SERVER_RESOURCES or _rclass.title() in orthanc_api.IMAGING_SERVER_RESOURCES:

				if _rclass.lower() in policy:
					policy[_rclass].update(_rgrant)
				else: policy[_rclass] = _rgrant

	return policy



# Decorator Functions

def orthancserver_basicauth(required_permission, 
		imagingserver_model=PacsImagingServer, apiaccess_model=ApiAccess, apiaccess_token_model=ApiAccessToken,
		serverid_fieldname='serverid'):
	''' Allows for the view to be accessed by the Orthanc Advanced Authorization plugin via basic authentication
		using an account username and token (for a password) or an access ID for username and secret for password.
		Also ensures that the user account has access to the requested imaging server and the specified permission.

		@input required_permission (function or string): Required permission may be
			either a Django permissions string or a callable function
			which accepts a user object as a parameter.

			If required_permission is a permissions string, the 
			user.has_perm method will be used to determine if the 
			user associated with the request has the required 
			permissions to access the requested resource.

			If a callable method or function, required_permission should
			take a user object and the Django request and then return True if the user
			has permissions to access the object or False if not.

			required_permission function signature (when passed a function):

			required_permission(suser, request)
				@input user (Django User): Django user model which should be checked for permission
				@input request (Django request object)
				@input vargs (tuple): Arguments provided to the view
				@input vkwargs (dict): Keyword arguments provided to the view

		@input apiaccess_model (Model subclass which implements BaseApiAccess API, default=secure.models.ApiAccess):
			Model which should be used to retrieve the access ID/secret key combination and determine
			whether the user has access to the requested resource.
		@input apiaccess_token_model (Model subclass which implements the BaseApiToken API, default=None): 
			Model which should be used to retrieve access tokens from and determine whether the user has access
			to the requested resource. When the model is None, token access is disabled.
	'''
	def decorator(view):

		@csrf_exempt
		@never_cache
		def _view(request, *args, **kwargs):

			# Retrieve imaging server
			try: server = imagingserver_model.objects.get(pk=kwargs.get(serverid_fieldname))
			except ObjectDoesNotExist as err:
				return guru_page_not_found(request, err)

			def check_userperms(suser):
				'''	Closure needed to verify that the user has the requried resources necessary to access the resource.

					@input user (Django User model object or subclass)
				'''
				if callable(required_permission): return required_permission(suser, request, args, kwargs)
				if isinstance(required_permission, str):
					return suser.has_perm(required_permission)
				
				raise TypeError('required_permission must either be a callable function or string')

			# Response for failed requests
			apiresponse = { gapi.API_STATUS: gapi.API_FAIL }

			# Retrive authentication parameters from the request
			if BASIC_AUTH_TYPE in request.headers.get('Authorization'):
				try:

					# Parse username/password from the Authorization header
					ucreds = base64.b64decode(request.headers.get('Authorization').replace(BASIC_AUTH_TYPE, '').strip()).decode('utf-8')
					if ':' in ucreds:
						uname,secret = ucreds.split(':')

						# Attempt to retrieve access ID credentials (Access ID as username, secret as password)
						try:
							apiaccess = apiaccess_model.objects.get(access_id=uname)
							if apiaccess.secret_key == secret:
								request.user = apiaccess.user
						
						# Failed to retrieve API access model, attempt retrieval of token model
						except ObjectDoesNotExist:
							apiaccess = apiaccess_token_model.objects.get(token=secret)
							if apiaccess.user.username == uname:
								request.user = apiaccess.user						

				except ObjectDoesNotExist:
					apiresponse[gapi.API_ERROR] = secureapi.API_INVALID_CREDENTIALS
					apiresponse[gapi.API_MESSAGE] = secureapi.API_ERROR_MISSING_CREDENTIALS

				except ValueError as err:
					logger.error('Unable to decode user credentials from authentication string')				

			# Check that PAI user has access to requested resource
			if getattr(request, 'user', None):
				
				try: upass = server.user_has_access(request.user) and check_userperms(request.user)
				except ObjectDoesNotExist as err:
					return guru_page_not_found(required_permission, err)

				# If permission, grant access
				if upass:
					return view(request, *args, **kwargs)

			# User checks failed
			return HttpResponseForbidden(json.dumps(apiresponse))

		return wraps(view)(_view)

	return decorator



# Permission functions

def api_permission_user_identity(user, request, vargs, vkwargs, 
		user_url_param='objectid', user_url_type=int):
	'''	Permission helper method for api_request which checks that a user is currently active
		and that the request user matches the user specified in the keyword arguments.
	'''
	# Convert user ID param to int
	try: url_userid = user_url_type(vkwargs.get(user_url_param))
	except ValueError as err: url_userid = vkwargs.get(user_url_param)
	
	return user.is_active and (user.is_superuser or user.pk == url_userid)


def api_permission_user_readonly(user, request, vargs, vkwargs):
	'''	Permission helper for api_request which checks that a user is currently active and
		requesting READ ONLY access to an API endpoint (GET). 

		@returns bool: True if the user is active, authenticated, and the request method is GET.
			False otherwise.
	'''
	return user.is_active and user.is_authenticated and request.method == HTTP_GET


def api_permission_user_readonly_admin_modify(user, request, vargs, vkwargs):
	'''	Permission helper for api_request which prevents requests to modify a resource
		unless the user has administrative privileges.
	'''
	# Allow access for read-only requests
	if not (user.is_superuser or user.is_staff):
		return 	api_permission_user_readonly(user, request, vargs, vkwargs)
	
	return user.is_active and user.is_authenticated and user.is_superuser


def api_permission_imageserver_user_readonly_admin_modify(user, request, vargs, vkwargs,
		imageserver_model=PacsImagingServer, server_url_param='objectid'):
	'''	Permission helper for api_request which prevents access to imaging server instances
		for which a user is not authorized. 
	'''
	# Authorize all admin access requests
	if user.is_active and user.is_authenticated and user.is_superuser:
		return True

	# Check user access to image server
	if api_permission_user_readonly_admin_modify(user, request, vargs, vkwargs):
		return imageserver_model.objects.filter(active=True).filter(pk=vkwargs.get(server_url_param)).filter(
			Q(user_authorizations__user=user) | Q(group_authorizations__group__user=user)).count() > 0
	
	return False


# OpenID Connect helper methods: these methods are used by the workflow views
# and by the Orthanc token validation views in order to enable validation of 
# remote tokens


def openid_get_django_user(authserver, socialuser_model, openid_username, authtoken, request=None):
	'''	Retrieve the auth profile associated with the OpenID username provided
		by the auth server. From that, fetch the user model. If the user does not exist,
		a username will be constructed from the data provided by the server.		

		Username processing:

		1. If available, parse the user handle portion of the email and use that
		2. For accounts without email data, convert the first name and last name to lowercase
			and then append them with a dot.
		3. For accounts without first name and last name, use the full name and replace
			spaces with a dot.
		4. For accounts without any identifiers, generate a random string to use as the username

		If the user profile does not exist, one will be created and the first login signal will
		be triggered.

		@input authserver (sonador.auth.models.SocialAuthorizationServer): authorization server
			instance and provider to be used for retrieving the user details.
		@input socialuser_model (sonador.auth.models.SocialUserAccount): social user account class to 
			be used for creating a Django user instance and associating it with the remote
			IdP account.
		@input openid_username (str): OpenID username retrieved form the identity provider
		@input authtoken (wgtauth.social.models.SocialAuthorizationToken): auth token provided
			by the identity provider

		@returns user instance
	'''
	# Attempt to retrieve social user profile via the unique provider ID (openid_username)
	try: socialuser_profile = authserver.social_user_profiles.get(social_user_id=openid_username)
	except socialuser_model.DoesNotExist:

		# Determine if there is currently a user logged in (link social profile to existing accout)
		if request and request.user.is_authenticated:
			django_user = request.user
			created = False

		# User not yet logged in: create a new account from the user data
		else:

			# Construct a username for the account:
			# 1. If available, parse the user handle portion of the email and use that
			# 2. For accounts without email data, convert the first name and last name to lowercase
			#    and then append them with a dot.
			# 3. For accounts without first name and last name, use the full name and replace
			#    spaces with a dot.
			# 4. For accounts without any identifiers, generate a random string to use as the username
			django_username = \
				authtoken.user.django_username if hasattr(authtoken.user, 'django_username') \
				else openid_username if openid_username \
				else authtoken.user.email.split('@')[0] \
					if hasattr(authtoken.user, 'email') and '@' in authtoken.user.email \
				else '.'.join((authtoken.user.first_name.lower(), authtoken.user.last_name.lower())) \
					if hasattr(authtoken.user, 'first_name') and hasattr(authtoken.user, 'last_name') \
				else authtoken.user.name.replace(' ', '.') if hasattr(authtoken.user, 'name') \
				else create_token()

			# Check if a user with the derived username already exists, if so, append the service
			# instance ID to the username in order to make it unique
			if auth.get_user_model().objects.filter(username=django_username).count():
				django_username = '%s.%s' % (django_username, authserver.pk)

			django_user = auth.get_user_model().objects.create(username=django_username,
				**pick(authtoken.user, ('first_name', 'last_name', 'email')))
			created = True

		# User profile does not exist, create a new user and profile from the service data,
		# trigger first login signal
		socialuser_profile = socialuser_model.objects.create(
			social_provider=authserver, user=django_user,
			social_user_id=openid_username, email=getattr(authtoken.user, 'email', None))
		socialuser_profile.signal_first_login(request=request, registration=created)

	return socialuser_profile.user
