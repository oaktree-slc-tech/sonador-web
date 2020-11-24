import logging, json, posixpath

from six.moves.urllib import parse as urlparse

from django.core.exceptions import PermissionDenied
from django.core import signing

from django.shortcuts import redirect, resolve_url
from django.urls import reverse
from django.utils.http import is_safe_url
from django.views.generic.base import View, TemplateView

from django.contrib import auth
from django.contrib.auth import views as auth_views

from guru.helpers import gsetting, create_token, site_fullurl
from guru.helpers.compatability import guru_permission_denied, guru_page_not_found, guru_bad_request
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
	OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_RESPONSE_TYPE_QUERY_PARAM, OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE
from wgtauth.social.views import OpenIDLoginRedirectAbstractView, \
	OpenIDLoginCallbackAbstractView
from wgtauth.registration.views import RegistrationView, RegistrationSuccessView, ConfirmEmailView, \
	SESSION_NEW_REGISTRATION_ATTR

from ...views.base import JSONBaseView
from ...helpers import SESSION_SALT, ACCESS_TOKEN_MAX_AGE
from ...apisettings import SONADOR_OHIF_CLIENTID, SONAODR_OHIF_REDIRECT_QUERY_PARAM

from ..models import SocialAuthorizationServer, SocialUserAccount
from ..forms import SonadorOpenIDConnectTokenAuthorizationForm

from .base import get_default_authserver, OpenIDAuthServerMixin

logger = logging.getLogger(__name__)


OPENID_AUTH_TOKEN_SESSION_PROVIDER_PARAM = 'openid-auth-provider'
OPENID_AUTH_TOKEN_SESSION_PARAM = 'openid-auth-token'
OPENID_AUTH_TOKEN_TYPE_SESSION_PARAM = 'openid-auth-token-type'
OPENID_AUTH_TOKEN_SCOPE_SESSION_PARAM = 'openid-auth-scope'


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
	'''
	ohif_redirect_fieldname = SONAODR_OHIF_REDIRECT_QUERY_PARAM

	def get_site_resource(self, request, vargs, vkwargs):
		redirect_url = super(OpenIDLoginRedirectView, self).get_site_resource(request, vargs, vkwargs)

		# Retrieve authserver for the redirect view
		if self.kwargs.get(self.authserver_objectid_url_param):
			authserver = self.get_auth_server(self.request, self.args, self.kwargs)
		else:
			authserver = get_default_authserver(authserver_model=self.authserver_model)

		# Encode state of the authorization_code request for unpacking after oAuth code workflow complete
		if not redirect_url and OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE in request.GET.get('response_type', []):
			logger.debug('Authorization code request components: %r' % request.GET)

			# Retrieve the OHIF provided redirect URL
			if request.GET.get(self.ohif_redirect_fieldname):
				ohif_redirect_url = request.GET.get(self.ohif_redirect_fieldname)

				# Ensure that the provided client ID matches that of the auth server
				if not authserver.client_id in request.GET.get('client_id'):
					raise PermissionDenied('Client ID provided in the request ("%s") does not match the auth server.'
						% request.GET.get('client_id'))

				# Ensure that the external redirect URL is included in the white list approved by the server. 
				if not authserver.is_safe_url(ohif_redirect_url):
					raise PermissionDenied(('Invalid redirect URL "%s". URL not registered with auth server '
						+ 'or part of the Sonador application.') % ohif_redirect_url)

				# Add the token endpoint for the server and ensure that the parameters are encoded so
				# they don't interefere with the code workflow.
				redirect_url = merge_url_querystring(authserver.url_token, request.GET.urlencode())
			
				# Create logic in the token view that also checks the white list for the auth server
				# before forwarding the authentication parameters.
				logger.debhg('Token endpoint with URL parameters for external authorization code request:\n%s' % redirect_url)
		
		return redirect_url


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
		authserver = self.get_auth_server(request, vargs, vkwargs)

		# Attempt to retrieve social user profile via the unique provider ID (openid_username)
		try: socialuser_profile = authserver.social_user_profiles.get(social_user_id=openid_username)
		except self.socialuser_model.DoesNotExist:

			# Determine if there is currently a user logged in (link social profile to existing accout)
			if request.user.is_authenticated:
				django_user = request.user
				created = False

			# User not yet logged in: create a new account from the user data
			else:

				# Construct a username for the account:
				# 1. If available, parse the user handle portion of the email and use that
				# 2. For accounts without email data, convert the first name and last name to lowercase
				#    and then append them with a dot.
				# 3. For accounts without first name and last name, use the full name and replace
				#    spaces with a dot.
				# 4. For accounts without any identifiers, generate a random string to use as the username
				django_username = \
					authtoken.user.django_username if hasattr(authtoken.user, 'django_username') \
					else openid_username if openid_username \
					else authtoken.user.email.split('@')[0] \
						if hasattr(authtoken.user, 'email') and '@' in authtoken.user.email \
					else '.'.join((authtoken.user.first_name.lower(), authtoken.user.last_name.lower())) \
						if hasattr(authtoken.user, 'first_name') and hasattr(authtoken.user, 'last_name') \
					else authtoken.user.name.replace(' ', '.') if hasattr(authtoken.user, 'name') \
					else create_token()

				# Check if a user with the derived username already exists, if so, append the service
				# instance ID to the username in order to make it unique
				if auth.get_user_model().objects.filter(username=django_username).count():
					django_username = '%s.%s' % (django_username, authserver.pk)

				django_user = auth.get_user_model().objects.create(username=django_username,
					**pick(authtoken.user, ('first_name', 'last_name', 'email')))
				created = True

			# User profile does not exist, create a new user and profile from the service data,
			# trigger first login signal
			socialuser_profile = self.socialuser_model.objects.create(
				social_provider=authserver, user=django_user,
				social_user_id=openid_username, email=getattr(authtoken.user, 'email', None))
			socialuser_profile.signal_first_login(request=request, registration=created)

		return socialuser_profile.user

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

		# oAuth configuration for specific server requested
		if self.kwargs.get(self.authserver_objectid_url_param):
			authserver = self.get_auth_server(self.request, self.args, self.kwargs)
			authserver_id = authserver.pk

		# oAuth configuration for default server requested
		else:
			authserver = get_default_authserver(authserver_model=self.authserver_model)
			authserver_id = None

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
				'response_types_supported': [OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE],
			})
		
		logger.debug('OpenID site configuration:\n%r' % openid_config)
		return openid_config


class oAuth2TokenAuthorizationView(OpenIDAuthServerMixin, GuruQueryParamMixin, View):
	'''	oAuth2Authorization endpoint that issues a signed access token for API calls
	'''
	tokenform_class = SonadorOpenIDConnectTokenAuthorizationForm
	ohif_redirect_fieldname = SONAODR_OHIF_REDIRECT_QUERY_PARAM

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
		
		if not tform.is_valid():
			logger.error('Invalid oAuth2 request. Validation errors\n%s'
				% formerrors2str(json.loads(tform.errors.as_json())))
			return guru_bad_request(request)

		# Retrieve authserver instance
		if self.kwargs.get(self.authserver_objectid_url_param):
			authserver = self.get_auth_server(self.request, self.args, self.kwargs)
		else:
			authserver = get_default_authserver(authserver_model=self.authserver_model)

		# Generate token and redirect
		rurl_odata = {
			'id_token': request.session.session_key,
			OAUTH_ACCESS_TOKEN: signing.dumps(request.session.session_key, salt=SESSION_SALT),
			OAUTH_TOKEN_TYPE: OAUTH_TOKEN_TYPE_BEARER,
			OAUTH_EXPIRATION: request.session.get_expiry_age(),
		}
		rurl_odata.update(pick(tform.cleaned_data, ('state',)))

		# Check redirect URL
		if not authserver.is_safe_url(tform.cleaned_data.get(self.ohif_redirect_fieldname)):
			raise PermissionDenied(('Invalid redirect URL "%s". URL not registered with auth server '
				+ 'or part of the Sonador application.') % ohif_redirect_url)

		# URL encode the response and redirect
		rurl = tform.cleaned_data.get(self.ohif_redirect_fieldname)+'?'+urlparse.urlencode(rurl_odata)
		logger.debug('Redirect URL: %s' % rurl)
		return redirect(rurl)


class oAuth2TokenRefreshView(GuruQueryParamMixin, View):
	'''	oAuthAuthorization endpoint that renews a signed session token
	'''
	def get(self, request, *args, **kwargs):

		# Ensure user is authenticated to the application
		if not hasattr(request, 'user') or not getattr(request.user, 'is_authenticated', False):
			return guru_permission_denied(request)
		
		return operation_results({
			'id_token': request.session.session_key,
			OAUTH_ACCESS_TOKEN: signing.dumps(request.session.session_key, salt=SESSION_SALT),
			OAUTH_TOKEN_TYPE: OAUTH_TOKEN_TYPE_BEARER,
			OAUTH_EXPIRATION: request.session.get_expiry_age(),
		})



class LoginView(OpenIDAuthServerMixin, auth_views.LoginView):
	'''	Login view for Sonador. Checks oAuth2 configuration for servers and automatically redirects
		if there is only a single server installed.
	'''
	authserver_model = SocialAuthorizationServer
	authserver_objectid_url_param = 'serverid'

	def get(self, *args, **kwargs):

		# oAuth configuration for specific server requested
		if self.kwargs.get(self.authserver_objectid_url_param):
			authserver = self.get_auth_server(self.request, self.args, self.kwargs)

		# oAuth configuration for default server requested
		else:
			authserver = get_default_authserver(authserver_model=self.authserver_model)

		# Retrieve default authserver for the platform
		if authserver:
			return redirect(authserver.url_login)

		return super(LoginView, self).get(*args, **kwargs)
