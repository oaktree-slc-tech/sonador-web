from wgtauth.forms import oAuthTokenAuthorizationForm
from wgtauth.apisettings import BASIC_AUTH_TYPE, \
	OAUTH_ACCESS_TOKEN, OAUTH_TOKEN_TYPE, OAUTH_TOKEN_TYPE_BEARER, OAUTH_EXPIRATION, \
	OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE


class SonadorOpenIDConnectTokenAuthorizationForm(oAuthTokenAuthorizationForm):
	'''	Token authorization form that will validate connection requests for both
		"token" and "authorization_code" requests.
	'''
	supported_token_workflows = (OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE)