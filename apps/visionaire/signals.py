'''	Signals and event handlers
'''
import logging

from django.db.models.signals import pre_save

from wgtauth.social.models import SocialAppProvider

from .auth.models import SocialAuthorizationServer

logger = logging.getLogger(__name__)


def authserver_check_token_validate(instance, instance_presave):
	'''	Check the authentication server to determine if the validate_token field changed.
		If so, disable token validation for any IdP instances which use the provider.
	'''
	# Token validation being removed from the provider instance: disable validation
	# for all affected IdP instances.
	if not instance.validate_token:

		# Retrieve social authorization servers with remote IdP token validation enabled
		for _idp in instance.socialauthorizationserver_set.filter(enable_idp_token_validation=True):

			# Disable and save
			_idp.enable_idp_token_validation = False
			_idp.save()


def oauth_provider_pre_save(sender, instance, *args, **kwargs):
	'''	Trigger checks and data synchroniztaion on IdP instances as a result of updates
		to the provider.
	'''
	try:

		# Retrieve instance of the provider from the database for comparison
		instance_presave = type(instance).objects.get(pk=instance.pk)

		# Ensure consistent token validation settings
		authserver_check_token_validate(instance, instance_presave)

	except type(instance).DoesNotExist: pass



# Connect signals for processing
pre_save.connect(oauth_provider_pre_save, sender=SocialAppProvider)
