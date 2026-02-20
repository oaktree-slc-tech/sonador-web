'''	Credential provider used for detecting Sonador managed API tokens
	
	1. Session tokens
	2. Standing API tokens
	3. Sonador system token (superduperuser)
'''
import logging
from guru.helpers import gsetting

from wgtauth.apisettings import BASIC_AUTH_TYPE, \
	OAUTH_ACCESS_TOKEN, OAUTH_TOKEN_TYPE, OAUTH_TOKEN_TYPE_BEARER, OAUTH_EXPIRATION, \
	OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE
from wgtauth import hexsigning
from wgtauth.services.credential_providers.base import ServiceAuthorizationRequest
from wgtauth.services.credential_providers.platform import PlatformCredentialProvider

from ....apisettings import SONADOR_USERNAME
from ....helpers import SESSION_SALT, ACCESS_TOKEN_MAX_AGE, \
	API_ACCESS_SERVER_TOKEN, API_ACCESS_TOKEN_QSPARAM, API_ACCESS_APITOKEN_QSPARAM, \
	API_REFERRER_REFERER_HEADER

logger = logging.getLogger(__name__)


class SonadorCredentialProvider(PlatformCredentialProvider):
	'''	Credential provider used for detecting and working with credentials issued by Sonador
	'''
	system_username = SONADOR_USERNAME
	system_apitoken = gsetting('SERVER_APITOKEN')
	session_salt = SESSION_SALT