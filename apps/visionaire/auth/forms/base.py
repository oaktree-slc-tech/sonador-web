import logging, six, copy, base64, traceback

from django import forms
from django.core import signing

from django.contrib import auth
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import Group

from guru.errors import OperationError
from guru.helpers import gsetting
from guru.helpers.urls import merge_url_querystring
from guru.helpers.utils.object import pick, omit

from secure.models import ApiAccess, ApiAccessToken
from secure.helpers import server_decrypt_data, masked_value

from wgtauth.apisettings import BASIC_AUTH_TYPE, \
	OAUTH_ACCESS_TOKEN, OAUTH_TOKEN_TYPE, OAUTH_TOKEN_TYPE_BEARER, OAUTH_EXPIRATION, \
	OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE

from ...apisettings import SONADOR_USERNAME
from ...helpers import SESSION_SALT, ACCESS_TOKEN_MAX_AGE, \
	API_ACCESS_SERVER_TOKEN, API_ACCESS_TOKEN_QSPARAM, API_ACCESS_APITOKEN_QSPARAM, \
	API_REFERRER_REFERER_HEADER

from .. import hexsigning

from .credential_providers.base import CredentialValidationError
from .credential_providers.sonador import SonadorCredentialProvider, ServiceAuthorizationRequest
from .credential_providers.cache import SonadorTokenCacheCredentialProvider
from .credential_providers.remote import SonadorRemoteCredentialProvider

logger = logging.getLogger(__name__)


class SonadorServiceAuthorizationBaseForm(forms.Form):
	''' Form instance which can be used to decode and verify token requests from services
		integrated with Sonador.

		@data-attr session (str): ID of the session associated with the user
		@data-attr token_payload (dict): key/value pairs of JSON encoded tokens
	'''
	token_key = forms.CharField(required=True)
	token_value = forms.CharField(required=True)
	cache_validation = False

	credential_providers = [
		SonadorCredentialProvider, SonadorTokenCacheCredentialProvider, SonadorRemoteCredentialProvider
	]

	def __init__(self, *args, **kwargs):

		self.cache_validation = kwargs.pop('cache_validation', self.cache_validation)
		super().__init__(*args, **kwargs)
		self.token_payload = None

	def _get_credential_provider_kwargs(self, credential_provider_class, options=None, **kwargs):
		'''	Retrieve the keyword arguments and options for the provided credential provider class.
		'''
		options = options or {}

		# Manage credential cache options		
		if credential_provider_class in (SonadorRemoteCredentialProvider, SonadorTokenCacheCredentialProvider):
			options['cache_validation'] = self.cache_validation
		return options

	def clean_authdata(self, cleaned_data, **kwargs):
		'''	Inspect authentication headers, convert to correct sessions or API tokens,
			retrieve users and permissions.
		'''
		for cred_provider in self.credential_providers:

			try:

				# Decode and parse the credential data
				_cred = cred_provider(cleaned_data, **self._get_credential_provider_kwargs(cred_provider, **kwargs))
				cleaned_data = _cred.clean()

				# Copy token payload and user attributes to form		
				self.token_payload = getattr(_cred, 'token_payload', None)
				self.expires_in = getattr(_cred, 'expires_in', None)
				self.user = getattr(_cred, 'user', None)
				self.session = getattr(_cred, 'session', None)

				return cleaned_data

			except CredentialValidationError as err:
				logger.debug('Unable to retrieve provided credentials for using provider=%s credential-key=%s credential-value=%s.\nError: %s.' % 
					(cred_provider.__name__, cleaned_data.get('token_key') or '', masked_value(cleaned_data.get('token_value') or ''), err))

		raise forms.ValidationError('Unable to validate provided credentials. Providers tried: %s'
			% ', '.join([_cred_provider.__name__ for _cred_provider in self.credential_providers]))
	