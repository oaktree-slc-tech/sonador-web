import logging, traceback

from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed

from wgtauth.social.models import SocialAuthorizationToken

from ...apisettings import OPENID_AUTH_TOKEN_SESSION_PROVIDER_PARAM, OPENID_AUTH_TOKEN_SESSION_PARAM, \
	OPENID_AUTH_TOKEN_TYPE_SESSION_PARAM

from ...audit import apisettings as audit_api
from ...audit.events import emit_audit_event

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


@receiver(user_logged_in)
def audit_user_login(sender, user=None, request=None, **kwargs):
	'''	Record a successful authentication.

		Log-in monitoring is what 45 CFR 164.308(a)(5)(ii)(C) asks for, and it is also what
		makes the resource-access records interpretable: without an authentication event
		there is no way to tie a run of study accesses back to a session.
	'''
	emit_audit_event(sender=sender, event_type=audit_api.AUDIT_USER_LOGIN,
		user=user, outcome=True, request=request)


@receiver(user_login_failed)
def audit_user_login_failed(sender, credentials=None, request=None, **kwargs):
	'''	Record a failed authentication attempt.

		Only the attempted username is recorded. Django scrubs password-like keys from
		`credentials` before sending this signal, and nothing else from the mapping is read
		here, so a mistyped password cannot reach the audit trail.

		The attempted username is a string rather than a user instance -- by definition no
		account was resolved -- which the actor resolution handles as an unauthenticated
		attempt.
	'''
	emit_audit_event(sender=sender, event_type=audit_api.AUDIT_USER_LOGIN_FAILED,
		user=(credentials or {}).get('username'), outcome=False, request=request)


@receiver(user_logged_out)
def audit_user_logout(sender, user=None, request=None, **kwargs):
	'''	Record the end of a session.

		Django sends `user_logged_out` before `session.flush()`, so `user` is still populated
		here. A logout following an anonymous session sends `user=None`, which is recorded as
		an unknown actor rather than dropped.
	'''
	emit_audit_event(sender=sender, event_type=audit_api.AUDIT_USER_LOGOUT,
		user=user, outcome=True, request=request)
