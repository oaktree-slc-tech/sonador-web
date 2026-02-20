import logging
from wgtauth.services.forms import DataServiceAuthorizationBaseForm

from .credential_providers.base import CredentialValidationError
from .credential_providers.sonador import SonadorCredentialProvider, ServiceAuthorizationRequest
from .credential_providers.cache import SonadorTokenCacheCredentialProvider
from .credential_providers.remote import SonadorRemoteCredentialProvider

logger = logging.getLogger(__name__)


class SonadorServiceAuthorizationBaseForm(DataServiceAuthorizationBaseForm):
	''' Form instance which can be used to decode and verify token requests from services
		integrated with Sonador.

		@data-attr session (str): ID of the session associated with the user
		@data-attr token_payload (dict): key/value pairs of JSON encoded tokens
	'''
	credential_providers = [
		SonadorCredentialProvider, SonadorTokenCacheCredentialProvider, SonadorRemoteCredentialProvider
	]
	cache_credential_providers = (SonadorRemoteCredentialProvider, SonadorTokenCacheCredentialProvider)
