import logging, six, copy, base64
from six.moves.urllib import parse as urlparse

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
from secure.helpers import server_decrypt_data

from wgtauth.apisettings import BASIC_AUTH_TYPE, \
	OAUTH_ACCESS_TOKEN, OAUTH_TOKEN_TYPE, OAUTH_TOKEN_TYPE_BEARER, OAUTH_EXPIRATION, \
	OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE

from ...helpers import SESSION_SALT, ACCESS_TOKEN_MAX_AGE, \
	API_ACCESS_SERVER_TOKEN, API_ACCESS_TOKEN_QSPARAM, API_ACCESS_APITOKEN_QSPARAM, \
	API_REFERRER_REFERER_HEADER

from .. import hexsigning

logger = logging.getLogger(__name__)


class ServiceAuthorizationRequest(object):
	'''	Stub object used to mock requests so that user instances can be retrieved from session
		by a service looking to authenticate a user.
	'''
	def __init__(self, session):
		self.session = session


class SonadorServiceAuthorizationBaseForm(forms.Form):
	''' Form instance which can be used to decode and verify token requests from services
		integrated with Sonador.

		@data-attr session (str): ID of the session associated with the user
		@data-attr token_payload (dict): key/value pairs of JSON encoded tokens
	'''
	token_key = forms.CharField(required=True)
	token_value = forms.CharField(required=True)

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.token_payload = None

	def decode_server_token_authdata(self, cleaned_data, tokenvalue_kw='token_value'):
		'''	Decode authentication data based on the Sonador server token
		'''
		svalue = copy.deepcopy(cleaned_data.get(tokenvalue_kw))
		logger.debug('Encrypted Sonador Server Token: %s' % svalue)

		try:

			# Convert the signed token to the encrypted server key
			ssig = svalue.replace(API_ACCESS_SERVER_TOKEN, '').strip()
			stoken = server_decrypt_data(signing.loads(ssig)).decode('utf-8')

			# Compare decrypted server token to local server token
			if stoken == gsetting('SERVER_APITOKEN'):
				self.user = 'sonador'
				self.expires_in = gsetting('AUTH_EXPIRES_IN_SERVERTOKEN')
				logger.debug('Authentication using Sonador server token')

		except signing.BadSignature as err:
			logger.error('Unable to decrypt server token from the provided value, bad signature.')

		return cleaned_data

	def decode_session_authdata(self, cleaned_data, tokenvalue_kw='token_value'):
		'''	Decode authentication data based on a Sonador session:

			1. base64 encoded JSON web tokens
			2. hex encoded session tokens
		'''
		svalue = copy.deepcopy(cleaned_data.get(tokenvalue_kw))
		logger.debug('Signed Session Token: %s' % svalue)

		try:

			# Convert the signed token to session key
			ssig = svalue.replace(OAUTH_TOKEN_TYPE_BEARER, '').strip()
			logger.debug('Bearer token: %s' % ssig)

			# Determine encoding of the token
			if ssig[:2] == 'h:':
				token_payload = self.decode_hex_authdata(ssig[2:])
			else:
				token_payload = self.decode_base64_authdata(ssig)

			# Retrieve session and other token payload data

			# String token payload: Django session ID
			if isinstance(token_payload, str):
				skey = token_payload

			# JSON token payload: session ID available from "session" key
			elif isinstance(token_payload, dict):
				skey = token_payload['session']
				self.token_payload = token_payload
				cleaned_data['token_payload'] = omit(token_payload, ('session',))

			else: raise TypeError('Unsupported token payload type: %s' % type(skey).__name__)

			logger.debug('Bearer token session: %s' % str(skey))
			cleaned_data['session'] = skey

			# Retrieve session from backend storage
			self.session = SessionStore(session_key=skey)
			self.user = auth.get_user(ServiceAuthorizationRequest(self.session))
			self.expires_in = gsetting('AUTH_EXPIRES_IN_SESSION')
			logger.debug('Token user: %s' % self.user.username)

		except signing.BadSignature as err:
			logger.error('Unable to retrieve session ID from the token, mismatched signature.\n%s'
				% cleaned_data.get(tokenvalue_kw))

		return cleaned_data

	def decode_base64_authdata(self, ssig):
		'''	Decode a Base64 session token
		'''
		return signing.loads(ssig, salt=SESSION_SALT)

	def decode_hex_authdata(self, ssig):
		'''	Decode a hexadecimal encoded session token
		'''
		return hexsigning.loads(ssig, salt=SESSION_SALT)
    
	def basicauth_check_accessid(self, cleaned_data, tokenvalue_kw='token_value'):
		'''	Decode base64 credentials, retrieve access ID from database, compare secret against
			secret value as a password check.
		'''
		svalue = copy.deepcopy(cleaned_data.get(tokenvalue_kw)).replace(BASIC_AUTH_TYPE, '').strip()

		try:
			ucreds = base64.b64decode(svalue).decode('utf-8')
			if ':' in ucreds:
				aid, secret = ucreds.split(':')
				logger.debug('Basic auth request with user access ID: %s' % aid)
				apiaccess = ApiAccess.objects.get(access_id=aid)

				# Check secret against that associated with the access ID
				if apiaccess.secret_key == secret:
					self.user = apiaccess.user
					self.expires_in = gsetting('AUTH_EXPIRES_IN_ORTHANC_PASSWORD')
					logger.debug('Basic auth with user access ID %s successful' % aid)
				else:
					logger.warning('Basic auth request denied for access ID %s. Provided secret does match.' % aid)

		except ValueError as err:
			logger.error('Unable to decode user credentials from authentication string')

		except ApiAccess.DoesNotExist:
			logging.error('Unable to retrieve user credentials, invalid access ID')

		return cleaned_data

	def clean_authdata(self, cleaned_data):
		'''	Inspect authentication headers, convert to correct sessions or API tokens,
			retrieve users and permissions.
		'''
		# Determine the correct token key/value keywords: referrer values take precedence if present
		if cleaned_data.get('referrer_token_key') and cleaned_data.get('referrer_token_value'):
			tokenvalue_kw = 'referrer_token_value'
		else: tokenvalue_kw = 'token_value'

		# Basic Authentication: Access ID/Secret Key
		if BASIC_AUTH_TYPE.lower() in cleaned_data.get(tokenvalue_kw, '').lower():
			cleaned_data = self.basicauth_check_accessid(cleaned_data, tokenvalue_kw=tokenvalue_kw)

		# Server (Sonador application) token
		elif (cleaned_data.get(tokenvalue_kw) and API_ACCESS_SERVER_TOKEN in cleaned_data.get(tokenvalue_kw)):

			# Parse base64 and encrypted token created using django.signing from application token value
			cleaned_data = self.decode_server_token_authdata(cleaned_data)

		# Bearer Token (oAuth: JWT/Hex Encoded)
		elif (cleaned_data.get(tokenvalue_kw) and OAUTH_TOKEN_TYPE_BEARER in cleaned_data.get(tokenvalue_kw)) \
			or (cleaned_data.get(tokenvalue_kw) == API_ACCESS_TOKEN_QSPARAM and OAUTH_TOKEN_TYPE_BEARER in cleaned_data.get(tokenvalue_kw)):

			# Parse base64 encoded token created using django.signing
			cleaned_data = self.decode_session_authdata(cleaned_data, tokenvalue_kw=tokenvalue_kw)

		# API token or referrer API token.
		# 1. The token key or referrer token key matches includes "token" or "api-token"
		# 2. The value includes "api-token"
		elif cleaned_data.get('token_key') in (API_ACCESS_TOKEN_QSPARAM, API_ACCESS_APITOKEN_QSPARAM) \
			or cleaned_data.get('referrer_token_key') in (API_ACCESS_TOKEN_QSPARAM, API_ACCESS_APITOKEN_QSPARAM) \
			or API_ACCESS_APITOKEN_QSPARAM in (cleaned_data.get('token_value') or '').lower():

			# Utilize referrer token value (if present) with first priority
			if cleaned_data.get('referrer_token_key'):
				tvalue = cleaned_data.get('referrer_token_value')
			else: tvalue = cleaned_data.get('token_value')

			# Remove "api-token" and trim (if present)
			if API_ACCESS_APITOKEN_QSPARAM in tvalue.lower():
				tvalue = tvalue.replace(API_ACCESS_APITOKEN_QSPARAM.lower(), '').replace(API_ACCESS_APITOKEN_QSPARAM.upper(), '').strip()

			# Retrieve API token and assign user
			try:
				t = ApiAccessToken.objects.select_related('user').get(pk__iexact=tvalue)
				self.user = t.user
				self.expires_in = gsetting('AUTH_EXPIRES_IN_SERVERTOKEN')
				logger.debug('Token user: %s' % self.user.username)

			except ApiAccessToken.DoesNotExist as err:
				logger.error('Unable to retrieve API token matching request: %s' % cleaned_data.get('token_value'))

		return cleaned_data
