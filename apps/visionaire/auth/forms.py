from wgtauth.forms import oAuthTokenAuthorizationForm
from wgtauth.apisettings import OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE


class SonadorOpenIDConnectTokenAuthorizationForm(oAuthTokenAuthorizationForm):
	'''	Token authorization form that will validate connection requests for both
		"token" and "authorization_code" requests.
	'''
	supported_token_workflows = (OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE)
	