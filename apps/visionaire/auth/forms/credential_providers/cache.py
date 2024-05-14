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

from .base import SonadorCredentialBaseProvider, ServiceAuthorizationRequest, CredentialValidationError

logger = logging.getLogger(__name__)


class SonadorTokenCacheCredentialProvider(SonadorCredentialBaseProvider):
	'''	Credential provider class which can be used to validate authorization tokens
		stored in Django session storage.
	'''
	cache_validation = False
	auth_credentials_max_age = gsetting('AUTH_CREDENTIALS_CACHE_MAX_AGE')
	auth_credentials_key_iterations = gsetting('AUTH_CREDENTIALS_CACHE_KEY_ITERATIONS')
	auth_credentials_hasher = PBKDF2PasswordHasher
	auth_sessionkey_length = gsetting('AUTH_CREDENTIALS_CACHE_SESSION_KEY_LENGTH')

	def __init__(self, *args, **kwargs):
		self.cache_validation = kwargs.pop('cache_validation', self.cache_validation)
		self.auth_credentials_max_age = kwargs.pop('auth_credentials_max_age', self.auth_credentials_max_age)
		self.auth_credentials_key_iterations = kwargs.pop('auth_credentials_key_iterations', self.auth_credentials_key_iterations)
		self.auth_credentials_hasher = kwargs.pop('auth_credentials_hasher', self.auth_credentials_hasher)

		super().__init__(*args, **kwargs)

	def clean(self, *args, sep='$', **kwargs):
		'''	Decode the credential data, check session storage for a key that matches a hashed
			version of the token, and retrieve the associated user.
		'''
		cleaned_data = self.data

		# Create one-way hash from the token
		if not self.cache_validation:
			raise CredentialValidationError('Credential cache is not enabled')

		# Esnure that the credential was provided as a bearer token
		if not OAUTH_TOKEN_TYPE_BEARER in cleaned_data.get('token_value', ''):
			raise CredentialValidationError('Invalid remote credential. Invalid auth type "%s"'
				% cleaned_data.get('token_value', '').split(' ')[0])

		try: 
			_token_str = cleaned_data.get('token_value', '').replace(OAUTH_TOKEN_TYPE_BEARER, '').strip()
			token_hash = self.auth_credentials_hasher().encode(_token_str, gsetting('SECRET_KEY'),
				iterations=self.auth_credentials_key_iterations)
			skey = binascii.hexlify(base64.b64decode(token_hash.split(sep)[-1])).decode('utf-8')

			# Retrieve session using hashed key
			self.session = SessionStore(session_key=skey[:self.auth_sessionkey_length])
			self.user = auth.get_user(ServiceAuthorizationRequest(self.session))
			self.expires_in = (self.session.get_expiry_date() - timezone.now()).seconds			

			if self.session.session_key and self.user.pk:
				return cleaned_data

		except Exception as err:
			logger.error('Unable to retrieve credentials from cache due to an error. Error: %s\n%s' % (
				err, traceback.format_exc()
			))

		raise CredentialValidationError('Unable to retrieved credentials from cache')