'''	Credentials provider for working with token instances that have been validated and stored
	as session variables.
'''
import logging, datetime, base64, binascii, traceback

from django.utils import timezone
from django.contrib import auth
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.contrib.sessions.backends.db import SessionStore

from guru.helpers import gsetting
from wgtauth.apisettings import OAUTH_TOKEN_TYPE_BEARER
from wgtauth.services.credential_providers.cache import DataServiceTokenCacheCredentialProvider

from .base import SonadorCredentialBaseProvider, ServiceAuthorizationRequest, CredentialValidationError

logger = logging.getLogger(__name__)


class SonadorTokenCacheCredentialProvider(DataServiceTokenCacheCredentialProvider):
	'''	Credential provider class which can be used to validate authorization tokens
		stored in Django session storage.
	'''
	