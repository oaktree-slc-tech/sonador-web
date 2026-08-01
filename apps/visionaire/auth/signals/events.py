import logging, traceback

from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_out

from wgtauth.social.models import SocialAuthorizationToken

from ...apisettings import OPENID_AUTH_TOKEN_SESSION_PROVIDER_PARAM, OPENID_AUTH_TOKEN_SESSION_PARAM, \
	OPENID_AUTH_TOKEN_TYPE_SESSION_PARAM

from ..models import SocialAuthorizationServer


logger = logging.getLogger(__name__)


@receiver(user_logged_out)
def revoke_openid_access_token(sender, user=None, request=None, **kwargs):
	'''	Revoke the identity provider access token when a Sonador session ends.

		Sonador's own session is what authenticates the viewer, and flushing it is what logs the
		user out. This handler deals with the separate credential Sonador holds on the user's
		behalf: the provider access token cached in the session by `cache_openid_tokendata`.
		Without this the token stays valid at the provider until it expires, outliving the session
		it was obtained for.

		Ordering matters and is safe: Django sends `user_logged_out` *before* `session.flush()`,
		so the cached token is still readable here.

		Revocation is best effort by design. A slow or unreachable provider must never turn a
		logout into an error page, so every failure is logged and swallowed -- the session flush
		that follows is the part that actually signs the user out.
	'''
	if request:

		authserverid = request.session.get(OPENID_AUTH_TOKEN_SESSION_PROVIDER_PARAM)
		if authserverid:

			# Retrieve authorization server
			try: authserver = SocialAuthorizationServer.objects.get(pk=authserverid)
			except SocialAuthorizationServer.DoesNotExist: authserver = None

			# Retrieve OpenID access token components
			openid_access_token = request.session.get(OPENID_AUTH_TOKEN_SESSION_PARAM)
			openid_token_type = request.session.get(OPENID_AUTH_TOKEN_TYPE_SESSION_PARAM)

			if authserver and openid_access_token and openid_token_type:

				try:
					authtoken = SocialAuthorizationToken(authserver, {
							'access_token': openid_access_token,
							'token_type': openid_token_type,
						})
					authtoken.revoke()

				except Exception as err:
					logger.error('Unable to revoke OpenID token %s from social provider %s due to an error:\n%s\n%s'
						% (openid_access_token, authserver.label_credentials, err, traceback.format_exc()))