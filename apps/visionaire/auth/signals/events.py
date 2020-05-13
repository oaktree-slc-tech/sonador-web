import six, logging, traceback

from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_out

from wgtauth.social.models import SocialAuthorizationToken


from ..models import SocialAuthorizationServer, SocialUserAccount
from ..views import OPENID_AUTH_TOKEN_SESSION_PROVIDER_PARAM, OPENID_AUTH_TOKEN_SESSION_PARAM, \
	OPENID_AUTH_TOKEN_TYPE_SESSION_PARAM, OPENID_AUTH_TOKEN_SCOPE_SESSION_PARAM


logger = logging.getLogger(__name__)


@receiver(user_logged_out)
def revoke_openid_access_token(sender, user=None, request=None, **kwargs):
	'''	Revoke OpenID access credentials on user logout
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