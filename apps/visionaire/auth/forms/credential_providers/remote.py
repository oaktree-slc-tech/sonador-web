'''	Credentials provider for working with remote identity provider (IdP) issued tokens
'''
import logging, datetime

from guru.helpers import gsetting
from wgtauth.apisettings import OAUTH_TOKEN_TYPE_BEARER

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

				# If the token validates, retrieve user and create session
				if _valid and datetime.datetime.utcnow() <= _valid_until:
					
					# Retrieve user details from IdP
					_auth_token = self._init_bearer_token(_auth_server, _token_str, valid_until=_valid_until_unix)
					_user = _auth_server.get_user(_auth_token)
					if not getattr(_user, 'username', None):
						raise ValueError('Unable to retrieve username from IdP instance')

					# Retrieve (or create) Django user instance and synchronize user properties
					self.user = openid_get_django_user(
						_auth_server, self.socialuser_model, _user.username, _auth_token)
					_auth_server.sync_idp_userinfo(self.user, _auth_token)
					
					# Add expiration time for validated token
					self.expires_in = gsetting('AUTH_EXPIRES_IN_SERVERTOKEN')

					return cleaned_data

			except Exception as err:
				raise CredentialValidationError('Unable to validate remote token due to an error. Error: "%s"' % err)

		raise CredentialValidationError('Unable to validate remote token')

	def validate_token(self, auth_server, token_str):
		'''	Verify access token with the provided auth server
		'''
		# Validate token from remote server
		_valid = auth_server.validate_token(self._init_bearer_token(auth_server, token_str))

		# Ensure that the token validation response includes both "valid" and "valid_until" components
		if not (len(_valid) == 2 and isinstance(_valid[0], bool) and isinstance(_valid[1], int)):
			raise ValueError('Incorrect value from auth server %s validate_token method "%s"' % (auth_server, _valid))

		return _valid[0], _valid[1]