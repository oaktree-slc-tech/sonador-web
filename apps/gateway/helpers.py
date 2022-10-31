import logging

from .models import ClinicalGateway

logger = logging.getLogger(__name__)


API_ALL_DEVICES_QSPARAM = 'all-devices'
API_ENV_INCLUDE_QSPARAM = 'env'
API_ENV_ALL_KEYS_QSPARAM = 'env-all-keys'



def api_permission_admin_device_owner(user, request, vargs, vkwargs,
		device_model=ClinicalGateway, device_url_param='objectid'):
	'''	Permission helper for api_request which checks to see that a user is currently active 
		and the owner of the device they are currently trying to access (or an administrative user).
	'''
	# Authorize admin requests
	if user.is_active and user.is_authenticated and user.is_superuser:
		return True

	# Check to determine if the user is the device owner
	device = device_model.objects.filter(pk=vkwargs.get(device_url_param)).first()
	if device and device.user == user:
		return True

	return False