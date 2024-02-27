from django.urls import re_path
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache

from guru.helpers import gsetting
from guru.forms import create_modelform_class
from secure.helpers import api_request
from secure.views import UserCredentialManagementView

from ..admin.auth import SonadorApiAccess, SonadorApiAccessToken
from ..helpers import API_ACCESS_APITOKEN_QSPARAM
from ..views.base import SonadorApiRestView

from .views.oauth import OpenIDLoginRedirectView, OpenIDLoginCallbackView, oAuth2EndpointsView, \
	oAuth2TokenAuthorizationView, CSRFTokenObtainView

from .views.service import orthanc
from .views.service import OrthancServiceAuthorizationView, OrthancSecureUriRedirectView

from .views.cred import SonadorUserCredentialManagementView, SonadorUserTokenManagementView, SonadorUserCredentialRestView
from .forms.cred import SonadorApiAccessTokenForm, SonadorApiAccessCredentialForm
from .helpers import orthancserver_basicauth


urlpatterns_openid_auth = [

	# oAuth2 Configuration
	re_path(r'.well-known/openid-configuration/?$', oAuth2EndpointsView.as_view(), name='openid-configuration-default'),

	# oAuth SSO: Reirect and Callback Views
	re_path(r'^(?P<serverid>\w+)/?$', OpenIDLoginRedirectView.as_view(), name='openid-login'),
	re_path(r'^(?P<serverid>\w+)/callback/?$', OpenIDLoginCallbackView.as_view(), name='openid-login-callback'),
	re_path(r'^(?P<serverid>\w+)/token/?$', login_required(oAuth2TokenAuthorizationView.as_view()), name='openid-auth-token'),
	re_path(r'^(?P<serverid>\w+)/.well-known/openid-configuration/?$', oAuth2EndpointsView.as_view(), name='openid-configuration'),

	# oAuth2 Based Token Authorization
	re_path(r'', login_required(oAuth2TokenAuthorizationView.as_view()), name='openid-auth-token-default'),
]


urlpatterns_service_auth = [

	# Orthanc authorization API
	re_path(r'^orthanc/(?P<serverid>\w+)/introspect/?$', 
		orthancserver_basicauth(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser)(
			OrthancServiceAuthorizationView.as_view()), name='service-orthanc'),
	re_path(r'^orthanc/(?P<serverid>\w+)/user-profile/?$', 
		orthancserver_basicauth(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser)(
			orthanc.OrthancAuthUserProfileView.as_view()), name='service-orthanc-user'),\
	re_path(r'^orthanc/(?P<serverid>\w+)/token-generate/(?P<token_type>[a-zA-Z0-9\-]+)?$',
		orthancserver_basicauth(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser)(
			orthanc.OrthancAuthTokenGenerateView.as_view()), name='service-orthanc-token-generate'),
	re_path(r'^orthanc/(?P<serverid>\w+)/token-decode/?$', 
		orthancserver_basicauth(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser)(
			orthanc.OrthancAuthTokenDecodeView.as_view()), name='service-orthanc-token-decode'),
	
	# Orthanc explorer (classic) and admin (OE2)
	re_path(r'^orthanc/(?P<serverid>\w+)/explorer/?$',
		login_required(
			OrthancSecureUriRedirectView.as_view(server_url_attr='url_admin', token_payload={ 'orthanc-resource': 'oe' })),
			name='orthanc-explorer-redirect'),
	re_path(r'^orthanc/(?P<serverid>\w+)/admin/?$',
		login_required(
			OrthancSecureUriRedirectView.as_view(server_url_attr='url_orthanc_explorer2', token_payload={ 'orthanc-resource': 'oe2' })),
			name='orthanc-admin-redirect'),
]


urlpatterns_auth_management = [

	# Sonador CSRF token obtain view
	re_path(r'^cred/csrf-token/?$',
		api_request(lambda user, request, vargs, vkwags: user.is_authenticated,
					allowed_http_methods_url_signature=('GET',),
					request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			CSRFTokenObtainView.as_view()),
		name='client-csrf-token'),

	# Credentials Management: access token
	re_path(r'^cred/token/?$',
		api_request(lambda user, request, vargs, vkwags: user.is_authenticated,
				apiaccess_token_model=SonadorApiAccessToken, 
				allowed_http_methods_url_signature=('GET', 'OPTIONS', 'POST', 'PUT', 'DELETE'),
				allowed_http_methods_token_access=('GET', 'OPTIONS', 'POST', 'PUT', 'DELETE'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			SonadorUserTokenManagementView.as_view(model=SonadorApiAccessToken, modelform=SonadorApiAccessTokenForm)),
		name='cred-management-access-token'),

	# Credentials Management: access ID/secret
	re_path(r'^cred/access/?$',
		api_request(lambda user, request, vargs, vkwags: user.is_authenticated,
				apiaccess_token_model=SonadorApiAccessToken, 
				allowed_http_methods_url_signature=('GET', 'OPTIONS', 'POST'),
				allowed_http_methods_token_access=('GET', 'OPTIONS', 'POST'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			SonadorUserCredentialManagementView.as_view(model=SonadorApiAccess, modelform=SonadorApiAccessCredentialForm)),
		name='cred-management-access-secret'),
	re_path(r'^cred/access/(?P<objectid>[a-zA-Z0-9]+)/?$',
		api_request(lambda user, request, vargs, vkwags: user.is_authenticated,
				apiaccess_token_model=SonadorApiAccessToken, allowed_http_methods_token_access=('GET', 'PATCH', 'PUT', 'DELETE'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			SonadorUserCredentialRestView.as_view(model=SonadorApiAccess, modelform=SonadorApiAccessCredentialForm)),
		name='cred-management-access-update'),
]
