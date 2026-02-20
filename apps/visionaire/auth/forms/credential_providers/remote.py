'''	Credentials provider for working with remote identity provider (IdP) issued tokens
'''
import logging
from wgtauth.services.credential_providers.remote import DataServiceRemoteCredentialProvider

from ...models import SocialAuthorizationServer, SocialUserAccount

logger = logging.getLogger(__name__)


class SonadorRemoteCredentialProvider(DataServiceRemoteCredentialProvider):
	'''	Credential provider class which can be used to validate authorization tokens from
		remote identity providers.
	'''
	authserver_model = SocialAuthorizationServer
	socialuser_model = SocialUserAccount
	