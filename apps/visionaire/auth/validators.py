'''	Validation for the authorization server's registered callback list.

	The token grant returns its response by appending parameters to the destination the client
	registered, so a registered entry may not already declare one of those names. Which names
	those are is a property of that response, so the field is validated against the grant's own
	set rather than the set another flow generates.
'''
from wgtauth.apisettings import OAUTH_ACCESS_TOKEN, OAUTH_TOKEN_TYPE, OAUTH_EXPIRATION
from wgtauth.services.redirects import validate_redirect_uri_configuration


# Parameters the oAuth2 token grant adds to the destination it redirects to. Used both to
# validate the registered callback list and to enforce the same rule at request time, so the
# two cannot disagree.
TOKEN_GRANT_RESPONSE_PARAMS = (
	'id_token', OAUTH_ACCESS_TOKEN, OAUTH_TOKEN_TYPE, OAUTH_EXPIRATION, 'state')


def validate_authserver_callback_url(value):
	'''	Validate an authorization server's registered callback list against the parameters the
		token grant generates.

		Defined at module level so it serializes into migrations by reference.
	'''
	return validate_redirect_uri_configuration(value,
		reserved_params=TOKEN_GRANT_RESPONSE_PARAMS)
