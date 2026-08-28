import logging, json, posixpath

from six.moves.urllib import parse as urlparse

from django.core.exceptions import PermissionDenied
from django.core import signing
from django.middleware import csrf

from django.shortcuts import redirect, resolve_url
from django.templatetags.static import static
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic.base import View, TemplateView

from django.contrib.sites.shortcuts import get_current_site

from django.contrib import auth
from django.contrib.auth import views as auth_views

from guru.helpers import gsetting, create_token, site_fullurl
from guru.helpers.compatability import guru_permission_denied, guru_page_not_found, guru_bad_request,\
	guru_is_safe_url
from guru.helpers import operation_results, site_fullurl
from guru.helpers.user import user_displayname
from guru.helpers.utils.object import pick, omit
from guru.helpers.utils.urls import merge_url_querystring
from guru.errors import ConfigurationError
from guru.views import GuruApiRestView
from guru.filter.views import GuruQueryParamMixin
from guru.helpers.utils.format import formerrors2str
from guru.helpers.utils.urls import build_url

from wgtauth.forms import oAuthTokenAuthorizationForm
from wgtauth.apisettings import OAUTH_ACCESS_TOKEN, OAUTH_TOKEN_TYPE, OAUTH_TOKEN_TYPE_BEARER, OAUTH_EXPIRATION, \
	OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_RESPONSE_TYPE_QUERY_PARAM, OAUTH_CODE_RESPONSE_TYPE, OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE
from wgtauth.services.redirects import append_response_parameters, \
	is_registered_redirect_uri, query_parameter_names
from wgtauth.social.views import OpenIDLoginRedirectAbstractView, \
	OpenIDLoginCallbackAbstractView
from wgtauth.registration.views import RegistrationView, RegistrationSuccessView, ConfirmEmailView, \
	SESSION_NEW_REGISTRATION_ATTR

from ...views.base import JSONBaseView
from ...helpers import SESSION_SALT, ACCESS_TOKEN_MAX_AGE
from ...apisettings import SONADOR_OHIF_CLIENTID, SONAODR_OHIF_REDIRECT_QUERY_PARAM, \
	OPENID_AUTH_TOKEN_SESSION_PROVIDER_PARAM, OPENID_AUTH_TOKEN_SESSION_PARAM, \
	OPENID_AUTH_TOKEN_TYPE_SESSION_PARAM, OPENID_AUTH_TOKEN_SCOPE_SESSION_PARAM

from ...models.branding import SonadorSite

from ..models import SocialAuthorizationServer, SocialUserAccount
from ..helpers import openid_get_django_user
from ..forms.oidc import SonadorOpenIDConnectTokenAuthorizationForm
from ..validators import TOKEN_GRANT_RESPONSE_PARAMS

from .base import get_default_authserver, OpenIDAuthServerMixin

logger = logging.getLogger(__name__)


def same_site_hosts():
	'''	Network locations which are this site.

		The canonical site location is added explicitly so a fully qualified site URL is
		recognised as its own host rather than by resembling one.

		@returns set of str: acceptable network locations
	'''
	_hosts = set(gsetting('ALLOWED_HOSTS') or ())
	_hosts.discard('*')

	_site = urlparse.urlsplit(site_fullurl() or '')
	if _site.netloc:
		_hosts.add(_site.netloc)

	return _hosts


def is_same_site_destination(destination):
	'''	Determine whether a destination belongs to the Sonador site itself, in which case the
		same-site policy applies rather than registration.

		Decided by comparing the parsed network location against the site's own. A destination
		is never rewritten to reach this answer: editing text out of an untrusted URL can turn
		one host into a relative path, which would let an unrelated destination inherit the
		same-site exception.

		@input destination (str): requested redirect destination

		@returns bool: True for a relative or Sonador-hosted destination
	'''
	return guru_is_safe_url(destination, allowed_hosts=same_site_hosts())


def is_authorized_client_destination(destination, authserver, reserved_params=()):
	'''	Determine whether a destination may receive an authorization response.

		A destination on this site keeps the same-site policy. Anything else receives
		credentials, so it has to match one complete registered callback rather than merely
		resembling one. The login redirect and the token grant share this rule so a request is
		refused before the identity provider round trip rather than after it.

		@input destination (str): requested redirect destination
		@input authserver: authorization server whose callbacks are registered
		@input reserved_params (iterable): names the response will generate, which the
			destination may therefore not already declare

		@returns bool: True when the destination may be redirected to
	'''
	# Malformed authority syntax raises here rather than parsing, so the destination is
	# refused instead of escaping as a server error. It is never repaired or normalized.
	try: _parts = urlparse.urlsplit(destination or '')
	except ValueError:
		return False

	if query_parameter_names(_parts.query) & set(reserved_params or ()):
		return False

	if is_same_site_destination(destination):
		return True

	return bool(authserver) and is_registered_redirect_uri(
		destination, authserver.callback_url, reserved_params=reserved_params)


class OpenIDViewPropertiesMixin(OpenIDAuthServerMixin):
	'''	View mixin which implements the interface required by OpenID authentication views
	'''
	def application_redirect_url(self, request, vargs, vkwargs):
		'''	Retrieve the login redirect/callback URL which should be used by the authentication service
		'''
		authserver = self.get_auth_server(request, vargs, vkwargs)
		return authserver.url_callback


class OpenIDLoginRedirectView(OpenIDViewPropertiesMixin, OpenIDLoginRedirectAbstractView):
	'''	Redirect user login requests to the specified OpenID provider for authentication. First step
		in the oAuth/OpenID authentication workflow.

		This redirect view implements two behaviors to allow external OHIF clients to authenticate:

		1. If an external client requests an "authorization_code" workflow, the view will capture the
			redirect URL, validate that is included in the whitelist for the auth server, and encoded
			it in the "state" parameter for redirect after completion of authentication with the auth
			server associated with the view instance.

		2. In cases where a client with a valid session connects to the view with an "authorization"
			request, the view will redirect to the token endpoint for the auth server. This emulates
			the behavior of the API endpoint which provides the token endpint as the auth endpoint
			for connected clients which provide a valid session cookie.
	'''
	ohif_redirect_fieldname = SONAODR_OHIF_REDIRECT_QUERY_PARAM

	def get_site_resource(self, request, vargs, vkwargs):
		'''	Retrieve a site resource that may be encoded as part of the oAuth URL.

			Special behavior: to facilitate oAuth requests from OHIF clients
			authenticating using the "authorization_code" workflow,
			the redirect URI of the client is captured (taken from the "state" parameter)
			and request URL parameters are encoded.
		'''
		redirect_url = super(OpenIDLoginRedirectView, self).get_site_resource(request, vargs, vkwargs)

		# Retrieve authserver for the redirect view
		authserver_id, authserver = self.get_auth_server_or_default(self.request, self.args, self.kwargs)

		# Encode OHIF authorization_code requests to pass to the token endpoint after a successful
		# authorization_code workflow.
		if not redirect_url and (OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE in request.GET.get('response_type', [])
				or OAUTH_CODE_RESPONSE_TYPE in request.GET.get('response_type', [])):

			# Retrieve the OHIF parameters provided redirect URL
			if request.GET.get(self.ohif_redirect_fieldname):
				ohif_redirect_url = request.GET.get(self.ohif_redirect_fieldname)

				# The client is an identity boundary, so it is compared exactly
				if request.GET.get('client_id') != authserver.client_id:
					raise PermissionDenied('Client ID does not match authserver=%s.' % authserver.pk)

				# The destination this forwards to is the one which will receive the issued
				# token, so it is held to the same rule the grant applies. Checking it here
				# refuses the request before the identity provider round trip.
				if not is_authorized_client_destination(ohif_redirect_url, authserver,
						reserved_params=TOKEN_GRANT_RESPONSE_PARAMS):
					raise PermissionDenied('Redirect URL is not registered with authserver=%s '
						'or part of the Sonador application.' % authserver.pk)

				# Add the token endpoint for the server and ensure that the parameters are encoded so
				# they don't interefere with the code workflow. The forwarded query carries values
				# the client compares on return -- its state, client ID, and redirect URI -- so it
				# is reserialized with its case intact rather than normalized.
				redirect_url = merge_url_querystring(authserver.url_token, request.GET.urlencode(),
					query_lowercase=False)

				# Create logic in the token view that also checks the white list for the auth server
				# before forwarding the authentication parameters.
				logger.debug('Forwarding external authorization code request to the token endpoint '
					'for authserver=%s' % authserver.pk)

		return redirect_url

	def get(self, request, *args, **kwargs):
		'''	Generate a 301 redirect to provider authorization URL

			Special behavior: to facilitate authentication requests from OHIF clients
			authenticating using the "authorization_code" workflow, forward to the
			token endpoint for the view authorization endpoint (after checking client_id).
		'''
		# For OHIF clients already authenticated to the platform, redirect to the token
		# endpoint for the auth server to allow them to refresh their code/token without
		# requiring offsite authentication a second time.
		if request.GET.get(self.ohif_redirect_fieldname):

			# Retrieve auth server for the view
			authserver_id, authserver = self.get_auth_server_or_default(self.request, self.args, self.kwargs)

			# Check user authentication, response type, and client ID
			if request.user.is_authenticated \
				and (OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE in request.GET.get('response_type', [])
					or OAUTH_CODE_RESPONSE_TYPE in request.GET.get('response_type', [])) \
				and authserver.client_id == request.GET.get('client_id'):

				# Redirect to token view for the server
				return redirect(authserver.url_token+'?'+request.GET.urlencode())

		return super(OpenIDLoginRedirectView, self).get(request, *args, **kwargs)


class OpenIDLoginCallbackView(OpenIDViewPropertiesMixin, OpenIDLoginCallbackAbstractView):
	'''	Callback endpoint to which system should redirect users which have been authenticated
		successfully. Completes the oAuth authentication workflow.
	'''
	socialuser_model = SocialUserAccount

	def get_site_resource(self, request, vargs, vkwargs):
		resource = super(OpenIDLoginCallbackView, self).get_site_resource(request, vargs, vkwargs)
		if resource:
			logger.debug('Site resource included in authentication request (state parameter):\n%s' % resource)
		
		return resource

	def get_openid_username(self, authtoken, request, vargs, vkwargs):
		'''	Retrieve the OpenID username via the authorization token
		'''
		openid_username = getattr(getattr(authtoken, 'user', None), 'username', None)
		if not openid_username:
			raise ConfigurationError(
				'Unable to retrieve OpenID username using auth token %s' % authtoken.access_token)

		return openid_username

	def get_django_user(self, openid_username, authtoken, request, vargs, vkwargs):
		'''	Retrieve the social auth profile associated with the OpenID username, and
			from that, fetch the user model.
		'''
		return openid_get_django_user(self.get_auth_server(request, vargs, vkwargs),
			self.socialuser_model, openid_username, authtoken, request=request)

	def cache_openid_tokendata(self, authtoken, user, request, vargs, vkwargs):
		'''	Cache the local token and other associated params in the session
			(so that it is available for other operations)
		'''
		# Cache a reference to the auth server instance used for generating the token
		authserver = self.get_auth_server(request, vargs, vkwargs)
		request.session[OPENID_AUTH_TOKEN_SESSION_PROVIDER_PARAM] = authserver.pk

		# Cache references to the access token and token type
		request.session[OPENID_AUTH_TOKEN_SESSION_PARAM] = authtoken.access_token
		request.session[OPENID_AUTH_TOKEN_TYPE_SESSION_PARAM] = authtoken.token_type


class oAuth2EndpointsView(OpenIDAuthServerMixin, JSONBaseView):
	'''	oAuth2 Endpoints for Sonador. The view can be configured to retrieve a specific
		authentication server by passing the server ID into a URL pattern, or the default server.
	'''

	def get_data(self, context):
		""" Returns oAuth OpenID configuration for Sonador.
		"""
		openid_config = super(oAuth2EndpointsView, self).get_data(context)

		# Retrieve oAuth server instance
		authserver_id, authserver = self.get_auth_server_or_default(self.request, self.args, self.kwargs)

		# OpenID base configuration
		openid_config.update({
			'token_endpoint': site_fullurl(
				reverse('auth:openid-auth-token', args=(authserver_id,)) if authserver_id  else reverse('auth:openid-auth-token-default')),
			'end_session_endpoint': site_fullurl(reverse('logout')),
		})

		# User already authenticated to the application, provide token endpoint
		# for the authorization and process login using "token grant" workflow.
		# (Used by the instance of OHIF integated into Sonador.)
		if self.request.user.is_authenticated:
			openid_config.update({
				'authorization_endpoint': site_fullurl(
					reverse('auth:openid-auth-token', args=(authserver_id,)) if authserver_id  else reverse('auth:openid-auth-token-default')),
				'response_types_supported': [OAUTH_TOKEN_RESPONSE_TYPE,],
			})

		# User not authenticated, provide OpenID login endpoint for authorization
		# and process login as a "code" workflow. Used by the OHIF instances that are
		# compiled as progressive web applications.
		else:
			openid_config.update({
				'authorization_endpoint': site_fullurl(authserver.url_login),
				'response_types_supported': [
					OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE, OAUTH_CODE_RESPONSE_TYPE,
				],
			})

		logger.debug('OpenID site configuration:\n%r' % openid_config)
		return openid_config


class oAuth2TokenAuthorizationView(OpenIDAuthServerMixin, GuruQueryParamMixin, View):
	'''	oAuth2Authorization endpoint that issues a signed access token for API calls
	'''
	tokenform_class = SonadorOpenIDConnectTokenAuthorizationForm
	ohif_redirect_fieldname = SONAODR_OHIF_REDIRECT_QUERY_PARAM
	session_salt = SESSION_SALT

	def get(self, request, *args, **kwargs):
		'''	Process an oAuth2 token request
		'''
		return self.oidc_tokengrant(request, *args, **kwargs)

	def oidc_tokengrant(self, request, *args, **kwargs):
		''' Process a token (grant) response
		'''
		# Ensure user is authenticated to the application
		if not hasattr(request, 'user') or not getattr(request.user, 'is_authenticated', False):
			return guru_permission_denied(request)

		# Ensure that all needed values for issuing the token were bad in the request
		tform = self.tokenform_class(
			self.getQueryStringData(request=request, vargs=args, vkwargs=kwargs))

		# A malformed request is answered as a bad request, not as a refusal: the destination
		# field is a URLField, so syntactically invalid input is rejected here, before there is
		# an authorization question to ask. A parseable but unauthorized destination is refused
		# below. Keeping the two distinct avoids reporting an unrelated missing field as a
		# refusal.
		if not tform.is_valid():
			logger.error('Invalid oAuth2 request. Validation errors\n%s'
				% formerrors2str(json.loads(tform.errors.as_json())))
			return guru_bad_request(request)

		# Retrieve authserver instance
		authserver_id, authserver = self.get_auth_server_or_default(self.request, self.args, self.kwargs)

		# Authorize the destination before a credential exists. The names the response will
		# generate are declared alongside the field validator, so the rule enforced here and
		# the rule the registration was checked against are the same.
		_destination = tform.cleaned_data.get(self.ohif_redirect_fieldname)

		if not is_authorized_client_destination(_destination, authserver,
				reserved_params=TOKEN_GRANT_RESPONSE_PARAMS):
			raise PermissionDenied('Redirect URL is not registered with the authorization server '
				'or part of the Sonador application, or declares a generated response parameter.')

		# Generate token and redirect
		rurl_odata = {
			'id_token': request.session.session_key,
			OAUTH_ACCESS_TOKEN: signing.dumps(request.session.session_key, salt=self.session_salt),
			OAUTH_TOKEN_TYPE: OAUTH_TOKEN_TYPE_BEARER,
			OAUTH_EXPIRATION: request.session.get_expiry_age(),
		}
		rurl_odata.update(pick(tform.cleaned_data, ('state',)))

		# Append the response to the destination's own query rather than starting a second
		# one, so a destination registered with a static query keeps it and the generated
		# parameters arrive as parameters.
		rurl = append_response_parameters(_destination, rurl_odata)

		# The response carries the issued token and the destination may carry a query, so
		# only its origin and path are recorded.
		_parts = urlparse.urlparse(_destination or '')
		logger.debug('Issuing token grant redirect to "%s"'
			% urlparse.urlunparse((_parts.scheme, _parts.netloc, _parts.path, '', '', '')))

		return redirect(rurl)


class oAuth2TokenRefreshView(GuruQueryParamMixin, View):
	'''	oAuthAuthorization endpoint that renews a signed session token
	'''
	session_salt = SESSION_SALT

	def get(self, request, *args, **kwargs):

		# Ensure user is authenticated to the application
		if not hasattr(request, 'user') or not getattr(request.user, 'is_authenticated', False):
			return guru_permission_denied(request)

		return operation_results({
			'id_token': request.session.session_key,
			OAUTH_ACCESS_TOKEN: signing.dumps(request.session.session_key, salt=self.session_salt),
			OAUTH_TOKEN_TYPE: OAUTH_TOKEN_TYPE_BEARER,
			OAUTH_EXPIRATION: request.session.get_expiry_age(),
		})



class OpenIDEndSessionView(OpenIDAuthServerMixin, View):
	'''	OpenID Connect RP-Initiated Logout endpoint for Sonador. This is the view published as
		`end_session_endpoint` by `oAuth2EndpointsView`, and it is what the viewer navigates to
		when a user picks "Logout" (oidc-client issues a top level GET to the end session
		endpoint, carrying `id_token_hint` and `post_logout_redirect_uri`).

		It replaces `django.contrib.auth.views.LogoutView` at the `logout` URL for two reasons:

		1.	`LogoutView` is POST-only from Django 5.0 onwards, so the spec mandated top level GET
			navigation from the relying party answers 405 and the session survives. The viewer then
			silently re-authenticates against the still-valid session cookie, which is the
			"logout does nothing" behavior reported in ohif-viewers#31.

		2.	`LogoutView` only honors its own `next` redirect field, so the `post_logout_redirect_uri`
			the relying party sends is discarded.

		The Django session is the authentication of record here: the bearer token the viewer holds
		is a signed copy of the session key (see `oAuth2TokenAuthorizationView`), so flushing the
		session is what actually signs the user out.

		NOTE: honoring GET means this endpoint is not CSRF protected, which is inherent to redirect
		based RP-initiated logout. The worst an attacker can force is an unwanted logout.
	'''
	http_method_names = ['get', 'head', 'post', 'options']
	redirect_uri_fieldname = 'post_logout_redirect_uri'
	state_fieldname = 'state'

	def get(self, request, *args, **kwargs):
		return self.end_session(request, *args, **kwargs)

	def post(self, request, *args, **kwargs):
		return self.end_session(request, *args, **kwargs)

	def end_session(self, request, *args, **kwargs):
		'''	Destroy the Sonador session and return the user to the post logout page
		'''
		# Resolve the redirect target *before* the session is destroyed: validating it reads
		# request state, and `auth.logout()` swaps in a fresh anonymous session.
		redirect_to, client_redirect = self.get_post_logout_redirect_url(request, args, kwargs)

		if getattr(request.user, 'is_authenticated', False):
			logger.debug('Ending Sonador session for "%s". Post logout redirect: %s'
				% (request.user, redirect_to))

		auth.logout(request)

		# RP-Initiated Logout 1.0 (section 2) requires `state` to be echoed back to the relying
		# party, but only when returning to an endpoint the relying party asked for.
		state = self.get_request_param(request, self.state_fieldname)
		if client_redirect and state:
			# `query_lowercase` must stay off: it lowercases the whole query string, which would
			# corrupt the opaque state value the relying party expects back verbatim.
			redirect_to = merge_url_querystring(
				redirect_to, {self.state_fieldname: state}, query_lowercase=False)

		return redirect(redirect_to)

	def get_request_param(self, request, fieldname):
		'''	Read a logout parameter from either the query string or a form post
		'''
		return request.POST.get(fieldname) or request.GET.get(fieldname)

	def get_default_redirect_url(self):
		'''	Page shown when the relying party does not ask for (or is not allowed) a specific
			destination. Confirms to the user that the logout completed.
		'''
		return resolve_url(gsetting('LOGOUT_REDIRECT_URL') or 'logout-success')

	def get_post_logout_redirect_url(self, request, vargs, vkwargs):
		'''	Resolve the destination for the user once the session has been destroyed.

			@returns tuple:
				1.	(str) URL to redirect to
				2.	(bool) True when the URL was requested by the relying party, False when it is
					the Sonador default. Only relying party destinations get `state` echoed back.
		'''
		requested = self.get_request_param(request, self.redirect_uri_fieldname)
		if not requested:
			return self.get_default_redirect_url(), False

		if not self.is_safe_redirect_url(request, vargs, vkwargs, requested):
			logger.warning(('Rejected post_logout_redirect_uri "%s": not a Sonador URL and not '
				+ 'registered with the authorization server. Falling back to the logout notice page.')
				% requested)
			return self.get_default_redirect_url(), False

		return requested, True

	def is_safe_redirect_url(self, request, vargs, vkwargs, url):
		'''	Determine whether the requested post logout destination may be redirected to.
			Guards the endpoint against being used as an open redirect.
		'''
		# `ALLOWED_HOSTS` may be a wildcard, which is meaningless for redirect validation. Check
		# against the host actually serving the request instead.
		allowed_hosts = set(gsetting('ALLOWED_HOSTS') or [])
		allowed_hosts.discard('*')
		allowed_hosts.add(request.get_host())

		# Relative URLs and fully qualified URLs belonging to the Sonador site itself
		if url_has_allowed_host_and_scheme(url, allowed_hosts=allowed_hosts, require_https=request.is_secure()):
			return True

		# Origins the platform already trusts as application endpoints. This is what lets the
		# viewer -- rather than Sonador -- finish the logout when it is not being served by
		# Sonador itself (a development server, or a standalone build on its own host). Without
		# it those deployments can never be returned to their own sign-out page, and every logout
		# ends on Sonador's fallback notice instead.
		if self.is_trusted_client_origin(url):
			return True

		# Endpoints registered verbatim with any of the configured authorization servers
		return any(authserver.is_safe_url(url, allowed_hosts=allowed_hosts)
			for authserver in self.get_auth_servers())

	def get_auth_servers(self):
		'''	Every authorization server configured for the platform.

			Deliberately not just the default/requested server: a viewer may be registered against
			any of them, and the destination is being validated, not authenticated.
		'''
		return self.authserver_model.objects.all()

	def is_trusted_client_origin(self, url):
		'''	Determine whether `url` is served from an origin the platform trusts as one of its
			own application endpoints.
		'''
		requested = urlparse.urlparse(url)
		if requested.scheme not in ('http', 'https') or not requested.netloc:
			return False

		for scheme, netloc in self.get_trusted_client_origins():
			if scheme != requested.scheme:
				continue
			if netloc == requested.netloc:
				return True

			# Wildcard subdomain form ("https://*.example.com"), matching how Django reads a
			# wildcard origin. The bare domain is intentionally not covered.
			if netloc.startswith('*.') and requested.netloc.endswith(netloc[1:]):
				return True

		return False

	def get_trusted_client_origins(self):
		'''	Origins (scheme, netloc) taken from the Callback URLs registered against the
			platform's authorization servers.

			The Callback URL list is the operator's record of which endpoints belong to the
			application, so it is the single source of truth here -- a viewer hosted somewhere
			other than Sonador is authorized by registering it there, not in site settings.
			Registering a client's callback declares that origin as part of the application, so
			the sign-out page served from the same origin is covered by the same entry.

			Relative and malformed entries are ignored.
		'''
		origins = set()

		for authserver in self.get_auth_servers():
			for entry in (authserver.callback_url or '').splitlines():
				registered = urlparse.urlparse((entry or '').strip())
				if registered.scheme in ('http', 'https') and registered.netloc:
					origins.add((registered.scheme, registered.netloc))

		return origins


class LogoutSuccessView(TemplateView):
	'''	Server rendered sign-out confirmation.

		The viewer renders its own sign-out page at the `post_logout_redirect_uri` (see
		`OhifSignedOutViewer`), which is where users normally land. This page is the fallback for
		everything that does not come back through the viewer: a direct hit on the logout URL, a
		relying party that sends no `post_logout_redirect_uri`, or a client that asks for one
		Sonador will not redirect to.

		The site's configurable farewell message is deliberately *not* rendered here: it is
		authored as markdown for the viewer's `ReactMarkdown` renderer, and Sonador carries no
		server side markdown dependency to render it with. This page states the outcome plainly
		instead.
	'''
	template_name = 'content/logout.html'

	def get_context_data(self, **kwargs):
		context = super(LogoutSuccessView, self).get_context_data(**kwargs)

		# Site branding, so the notice matches the viewer the user just left
		site = get_current_site(self.request)
		ssite = SonadorSite.objects.filter(pk=site.pk).first()

		context['site'] = ssite if ssite else site
		context['logo'] = ssite.logo.url if (ssite and ssite.logo) else static('images/sonador-logo.ng.svg')

		return context


class LoginView(OpenIDAuthServerMixin, auth_views.LoginView):
	'''	Login view for Sonador. Checks oAuth2 configuration for servers and automatically redirects
		if there is only a single server installed.
	'''
	authserver_model = SocialAuthorizationServer
	authserver_objectid_url_param = 'serverid'

	def get(self, *args, **kwargs):

		# Retrieve authserver instance
		authserver_id, authserver = self.get_auth_server_or_default(self.request, self.args, self.kwargs)
		if authserver:
			return redirect(authserver.url_login)

		return redirect(reverse('admin:login')+'?'+self.request.GET.urlencode())


class CSRFTokenObtainView(GuruQueryParamMixin, View):
	"""
	CSRF token obtain view returns csrf token for frontend, has basic auth
	"""

	def get(self, request, *args, **kwargs):
		# Ensure user is authenticated to the application
		if not hasattr(request, 'user') or not getattr(request.user, 'is_authenticated', False):
			return guru_permission_denied(request)

		token = csrf.get_token(request)
		return operation_results({
			'csrf_token': token,
		})
