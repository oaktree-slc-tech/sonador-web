from django.conf.urls import url
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache

from guru.helpers import gsetting

from .views.oauth import OpenIDLoginRedirectView, OpenIDLoginCallbackView, oAuth2EndpointsView, \
	oAuth2TokenAuthorizationView
from .views.service import OrthancServiceAuthorizationView, OrthancSecureUriRedirectView


urlpatterns_openid_auth = [

	# oAuth2 Configuration
	url(r'.well-known/openid-configuration/?$', oAuth2EndpointsView.as_view(), name='openid-configuration-default'),

	# oAuth SSO: Reirect and Callback Views
	url(r'^(?P<serverid>\w+)/?$', OpenIDLoginRedirectView.as_view(), name='openid-login'),
	url(r'^(?P<serverid>\w+)/callback/?$', OpenIDLoginCallbackView.as_view(), name='openid-login-callback'),
	url(r'^(?P<serverid>\w+)/token/?$', login_required(oAuth2TokenAuthorizationView.as_view()), name='openid-auth-token'),
	url(r'^(?P<serverid>\w+)/.well-known/openid-configuration/?$', oAuth2EndpointsView.as_view(), name='openid-configuration'),

	# oAuth2 Based Token Authorization
	url(r'', login_required(oAuth2TokenAuthorizationView.as_view()), name='openid-auth-token-default'),
]


urlpatterns_service_auth = [

	# Orthanc
	url(r'^orthanc/(?P<serverid>\w+)/auth/?$', csrf_exempt(never_cache(OrthancServiceAuthorizationView.as_view())), name='service-orthanc'),
	url(r'^orthanc/(?P<serverid>\w+)/admin/?$',
		login_required(OrthancSecureUriRedirectView.as_view(server_url_attr='url_admin')), name='orthanc-admin-redirect'),
	url(r'^orthanc/(?P<serverid>\w+)/dicom-web/?$',
		login_required(OrthancSecureUriRedirectView.as_view(server_url_attr='url_dicomweb_client')), name='orthanc-dicomweb-redirect'),
]

