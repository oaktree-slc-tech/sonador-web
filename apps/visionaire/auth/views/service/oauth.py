'''	View classes which support OpenID Connect authentication workflows via Sonador Data Services
'''
import logging

from django.core.exceptions import PermissionDenied

from guru.helpers.compatability import guru_page_not_found, guru_permission_denied
from guru.helpers.utils.urls import merge_url_querystring, urlparse, build_url
from guru.helpers.utils.object import pick

from secure.helpers import server_encrypt_data, server_decrypt_data

from wgtauth import hexsigning
from wgtauth.apisettings import OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE, OAUTH_REDIRECT_QUERY_PARAM, \
	OAUTH_TOKEN_TYPE_BEARER
from wgtauth.services.views.oauth import DataServiceOpenIDLoginRedirectAbstractView, \
	DataServiceOpenIDLoginCallbackAbstractView, DataServiceOpenIDTokenAuthorizationView
from wgtauth.services.helpers import create_session_token

from ..base import get_default_authserver
from ...models import DataService, SocialAuthorizationServer, SocialUserAccount
from ...helpers import SESSION_SALT

logger = logging.getLogger(__name__)


class SonadorDataServiceOpenIDViewPropertiesMixin:
	'''	Mixin providing methods for interacting with data service associated auth servers.
	'''
	authserver_model = SocialAuthorizationServer
	
	def get_auth_server(self, request, vargs, vkwargs):
		'''	Retrieve the auth server associated with the data server
		'''
		# Attempt to retrieve server from cache
		authserver = self.kwargs.get('authserver')

		# Not available from cache, retrieve from the database and place in view keyword arguments
		if not authserver:
			dataservice = self.get_dataservice(request, vargs, vkwargs)
			authserver = dataservice.authserver or get_default_authserver(authserver_model=self.authserver_model)

		return authserver


class SonadorDataServiceOpenIDLoginRedirectView(
		SonadorDataServiceOpenIDViewPropertiesMixin, DataServiceOpenIDLoginRedirectAbstractView):
	'''	Redirect user login request to an auth service associated with a data service.
	'''
	model = DataService
	service_redirect_fieldname = OAUTH_REDIRECT_QUERY_PARAM
	
	def application_redirect_url(self, request, vargs, vkwargs):
		'''	Retrieve the URL for the authserver attached to the data service
		'''
		authserver = self.get_auth_server(request, vargs, vkwargs)
		return authserver.url_callback

	def get_site_resource(self, request, vargs, vkwargs):
		'''	Data service requests always forward an associated auth server within Sonador,
			and need to capture/encode redirect requests.
		'''
		site_resource = super().get_site_resource(request, vargs, vkwargs) \
			or self.get_dataservice_resource(request, vargs, vkwargs)

		# Encode data service code requests to pass to the token endpoint after a successful code workflow
		if self.has_dataservice_oidc_redirect(request, vargs, vkwargs) and site_resource:
			logger.warn('Authorization code request components: %r' % request.GET)
			dataservice = self.get_dataservice(request, vargs, vkwargs)

			# Ensure that the provided client ID matches that of the data service
			if not dataservice.openid_client_id in request.GET.get('client_id', []):
				raise PermissionDenied('Client ID provided in the request ("%s") does not match the data service.'
					% request.GET.get('client_id', '(null)'))

			# Because data service OpenID connect workflows rely upon auth servers to mediate them,
			# the redirect URL needs to be encoded twice. The callback endpoint for the service
			# needs to be embedded (with the redirect attached) and then the auth server token 
			# endpint needs to be placed in front of that value.
			site_resource = merge_url_querystring(
				dataservice.url_callback, request.GET.urlencode())

			logger.warn('Data service callback endpoint with URL parameters:\n%s' % site_resource)

		return site_resource


class SonadorDataServiceOpenIDLoginCallbackView(
		SonadorDataServiceOpenIDViewPropertiesMixin, DataServiceOpenIDLoginCallbackAbstractView):
	'''	Callback endpoint to which system sholud redirect users which have been authenticated successfully.
		Completes the authentication workflow. Data service mediated callback views trigger after
		the user has been processed by the Sonador auth server. For that reason, it's possible to 
		directly retrieve the user form the request rather than needing to parse the auth token
		and fetch the user via the socialuser_model.
	'''
	model = DataService
	socialuser_model = SocialUserAccount
	session_salt = SESSION_SALT

	def application_redirect_url(self, request, vargs, vkwargs):
		'''	Retrieve the login redirect/callback URL for the associated data service
		'''
		dataservice = self.get_dataservice(request, vargs, vkwargs)
		return dataservice.url_callback

	def get_site_resource(self, request, vargs, vkwargs):
		'''	Retrieve the resource 
		'''
		# Retrieve site or data service redirect URL
		resource = super().get_site_resource(request, vargs, vkwargs) \
			or self.get_dataservice_resource(request, vargs, vkwargs)
		if resource:
			logger.debug('Site resource included in authentication request (state parameter):\n%s' % resource)

		# For data service mediated workflows, attach a "code" which will allow the client application to 
		# exchange the code for an authorizaton token.
		if self.has_dataservice_oidc_redirect(request, vargs, vkwargs):
			resource = self.encode_dataservice_authcode_redirect(resource, request)

		return resource

	def is_safe_url(self, authserver, site_resource):
		'''	Determine if the provided site resource is safe to redirect to
		'''
		# Determine type of redirect and ensure that the redirect is safe. For OIDC resources
		# (which include a response_type == 'authorization_code' and a redirect_uri), 
		# check the whitelist defined on the data service. For all other site resources,
		# the auth server instance is used.
		if self.has_dataservice_oidc_redirect(self.request, self.args, self.kwargs):
			dataservice = self.get_dataservice(self.request, self.args, self.kwargs)			

			# Filter query params, params, and fragment for matching against the OpenID callback URL list
			# so that the direct match only considers scheme, netloc, and path
			_r = urlparse.urlparse(site_resource)
			return build_url(**pick(_r, ('scheme', 'netloc', 'path'))) in dataservice.openid_callback_url

		return authserver.is_safe_url(site_resource)


class SonadorDataServiceOpenIDTokenAuthorizationView(DataServiceOpenIDTokenAuthorizationView):
	'''	View class which is used by Sonador Data Services to exchange OIDC codes for tokens.
		Ensures that the user is a member of the data service before returning the token instance.
	'''
	model = DataService
	session_salt = SESSION_SALT
