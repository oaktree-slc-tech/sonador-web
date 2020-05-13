from django.db.models import Q, Subquery
from django.apps import apps

def api_permission_user_identity(user, request, vargs, vkwargs, 
		user_url_param='objectid', user_url_type=int):
	'''	Permission helper method for api_request which checks that a user is currently active
		and that the request user matches the user specified in the keyword arguments.
	'''
	# Convert user ID param to int
	try: url_userid = user_url_type(vkwargs.get(user_url_param))
	except ValueError as err: url_userid = vkwargs.get(user_url_param)
	
	return user.is_active and (user.is_superuser or user.pk == url_userid)
	