'''	Credentials provider for working with remote identity provider (IdP) issued tokens
'''
import logging, datetime, traceback, base64, binascii

from django.contrib import auth as django_auth
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.utils import timezone as django_timezone

from guru.helpers import gsetting
from guru.errors import ConfigurationError
from wgtauth.apisettings import OAUTH_TOKEN_TYPE_BEARER

from ....apisettings import OPENID_AUTH_TOKEN_SESSION_PROVIDER_PARAM, \
	OPENID_AUTH_TOKEN_SESSION_PARAM, OPENID_AUTH_TOKEN_USER
from ...models import SocialAuthorizationServer, SocialUserAccount
from ...helpers import openid_get_django_user

from .base import SonadorCredentialBaseProvider, CredentialValidationError

logger = logging.getLogger(__name__)


class SonadorRemoteCredentialProvider(SonadorCredentialBaseProvider):
	'''	Credential provider class which can be used to validate authorization tokens from
		remote identity providers.
	'''
	authserver_model = SocialAuthorizationServer
	socialuser_model = SocialUserAccount
	
	# Credential cache
	cache_validation = False
	auth_credentials_max_age = gsetting('AUTH_CREDENTIALS_CACHE_MAX_AGE')
	auth_credentials_key_iterations = gsetting('AUTH_CREDENTIALS_CACHE_KEY_ITERATIONS')
	auth_credentials_hasher = PBKDF2PasswordHasher
	auth_sessionkey_length = gsetting('AUTH_CREDENTIALS_CACHE_SESSION_KEY_LENGTH')

	def __init__(self, *args, **kwargs):
		self.cache_validation = kwargs.pop('cache_validation', self.cache_validation)
		self.auth_credentials_max_age = kwargs.pop('auth_credentials_max_age', self.auth_credentials_max_age)
		self.auth_credentials_key_iterations = kwargs.pop(
			'auth_credentials_key_iterations', self.auth_credentials_key_iterations)
		self.auth_credentials_hasher = kwargs.pop('auth_credentials_hasher', self.auth_credentials_hasher)
		self.auth_sessionkey_length = kwargs.pop('auth_sessionkey_length', self.auth_sessionkey_length)

		super().__init__(*args, **kwargs)
		self.auth_server = None

	def _init_bearer_token(self, auth_server, token_str, 
			token_type=OAUTH_TOKEN_TYPE_BEARER, valid_until=None):
		'''	Initialize a bearer token instance from the provided string

			@input auth_server (SocialAuthorizationServer): auth server instance
			@input token (str): 
		'''
		_token = {
			auth_server.authtoken_class.access_token_attr: token_str.strip(),
			auth_server.authtoken_class.access_token_type_attr: token_type.lower(),
		}

		# Add expiration (if provided)
		if valid_until:
			_token['exp'] = valid_until

		return auth_server.authtoken_class(auth_server, _token)

	def clean(self, *args, **kwargs):
		'''	Decode the credential data and retrieve the associated user
		'''
		cleaned_data = self.data

		# Iterate through servers with remote token validation and attempt to verify the credentials
		for _auth_server in self.authserver_model.objects.filter(enable_idp_token_validation=True):

			# Ensure that the credential was provided as a bearer token
			if not OAUTH_TOKEN_TYPE_BEARER in cleaned_data.get('token_value', ''):
				raise CredentialValidationError('Invalid remote credential. Invalid auth type "%s"' 
					% cleaned_data.get('token_value', '').split(' ')[0])

			# Remove "Bearer" from token payload and validate using auth server
			try: 

				# Verify token instance with authorization provider
				_token_str = cleaned_data.get('token_value', '').replace(OAUTH_TOKEN_TYPE_BEARER, '').strip()
				_valid, _valid_until_unix = self.validate_token(_auth_server, _token_str)
				_valid_until = datetime.datetime.utcfromtimestamp(_valid_until_unix)
				_now = datetime.datetime.utcnow()				

				# If the token validates, retrieve user and create session
				if _valid and _now <= _valid_until:
					
					# Retrieve user details from IdP
					_auth_token = self._init_bearer_token(_auth_server, _token_str, valid_until=_valid_until_unix)
					_user = _auth_server.get_user(_auth_token)					

					if not getattr(_user, 'username', None):
						raise ValueError('Unable to retrieve username from IdP instance')

					# Retrieve (or create) Django user instance and synchronize user properties
					self.user = openid_get_django_user(
						_auth_server, self.socialuser_model, _user.username, _auth_token)
					_auth_server.sync_idp_userinfo(self.user, _auth_token)
					
					# Add expiration time for validated token: should be the shorter of the following:
					# * _valid_until - _now
					# * number of seconds specified in the AUTH_EXPIRES_IN_SERVERTOKEN setting for the
					#   Sonador instance
					_expires_in = _valid_until - _now					
					self.expires_in = _expires_in.seconds if \
						_expires_in.seconds <= gsetting('AUTH_EXPIRES_IN_SERVERTOKEN') else gsetting('AUTH_EXPIRES_IN_SERVERTOKEN')

					# Add reference to auth server used to grant the token
					self.auth_server = _auth_server

					# Cache credentials
					if self.cache_validation:
						self.cache_credentials(_token_str, _valid_until)

					return cleaned_data

			except Exception as err:
				emsg = 'Unable to validate remote token due to an error. Error: "%s"' % err
				logger.error('%s\n%s' % (emsg, traceback.format_exc()))

		raise CredentialValidationError('Unable to validate remote token. Providers: %s' 
			% ', '.join('"%s"' % _p for _p in self.authserver_model.objects.filter(enable_idp_token_validation=True)))

	def validate_token(self, auth_server, token_str):
		'''	Verify access token with the provided auth server
		'''
		# Validate token from remote server
		_valid = auth_server.validate_token(self._init_bearer_token(auth_server, token_str))

		# Ensure that the token validation response includes both "valid" and "valid_until" components
		if not (len(_valid) == 2 and isinstance(_valid[0], bool) and isinstance(_valid[1], int)):
			raise ValueError('Incorrect value from auth server %s validate_token method "%s"' % (auth_server, _valid))

		return _valid[0], _valid[1]

	def cache_credentials(self, token_str, valid_until, *args, sep='$', **kwargs):
		'''	Save a copy of the user credentials 
		'''
		# Ensure that the provider located a valid user
		if not self.user:
			raise ValueError('Unable to cache credentials, invalid user instance')

		# Ensure that the provider has a reference to the auth server
		if not self.auth_server:
			raise ValueError('Unable to cache credentials, invalid auth server instance')

		# Determine expiration of the token. Tokens should be valid for the remaining lifetime
		# or the maximum cache age, whichever is shortest.
		_now = datetime.datetime.utcnow()
		_expires_in = valid_until -_now
		if _expires_in.seconds >= self.auth_credentials_max_age:
			_expires_in = datetime.timedelta(seconds=self.auth_credentials_max_age)

		# Create a one-way hash from the token string to create a session key.
		# Django's password hashers return a 4-part string with the algorithm, number of iterations,
		# secret/salt, and the signature delineated by a dollar sign. Signatures are base64 encoded.
		# For the session key only the signature is stored. Cached credentials will be checked 
		# by SonadorTokenCacheCredentialProvider.
		token_hash = self.auth_credentials_hasher().encode(token_str, gsetting('SECRET_KEY'), 
			iterations=self.auth_credentials_key_iterations)

		# Create hexadecimal encoded hash to prevent issues with reserved keys in Django session storage
		skey = binascii.hexlify(base64.b64decode(token_hash.split(sep)[-1])).decode('utf-8')

		# Retrieve auth backends
		_auth_backends = django_auth._get_backends(return_tuples=True)
		if len(_auth_backends) == 1:
			_, _auth_backend = _auth_backends[0]
		else:
			raise ConfigurationError('Invalid authentication backend configuration. The Sonador token cache '
				+ 'only supports a single auth backend being active at a time.')

		_s = Session.objects.filter(session_key=skey[:self.auth_sessionkey_length]).first()
		if _s: _s.delete()

		# Create a session using the token derived key
		Session(pk=skey[:self.auth_sessionkey_length], expire_date=django_timezone.now()+_expires_in).save()
		
		# Initialize session storage, cache references to the user, auth server, and token.
		s = SessionStore(session_key=skey[:self.auth_sessionkey_length])
		s[django_auth.SESSION_KEY] = self.user._meta.pk.value_to_string(self.user)
		s[django_auth.BACKEND_SESSION_KEY] = _auth_backend
		s[django_auth.HASH_SESSION_KEY] = self.user.get_session_auth_hash()

		# Add token and auth server identifiers to session
		s[OPENID_AUTH_TOKEN_SESSION_PARAM] = token_str
		s[OPENID_AUTH_TOKEN_SESSION_PROVIDER_PARAM] = self.auth_server.pk
		
		# Set expiration and save
		s.set_expiry(_expires_in)
		s.save()