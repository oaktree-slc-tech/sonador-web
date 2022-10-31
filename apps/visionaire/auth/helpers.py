from django.db.models import Q, Subquery
from django.apps import apps

from guru.apisettings import HTTP_GET

from ..models.servers import PacsImagingServer


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