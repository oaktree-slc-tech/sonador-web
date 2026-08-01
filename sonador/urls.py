import os

from django.urls import include
from django.urls import path, re_path

from django.contrib import admin
from django.contrib.auth.decorators import login_required

from guru.helpers import gsetting
from guru import apisettings as gapicodes

from visionaire import visionaire_app_name
from visionaire.auth.views import LoginView, LogoutSuccessView, OpenIDEndSessionView, \
    oAuth2TokenAuthorizationView, oAuth2TokenRefreshView
from visionaire.auth.views.service import OrthancSecureUriRedirectView
from visionaire.views import OhifConfigView, OhifDicomViewer, OhifSignedOutViewer
from visionaire.auth.urls import urlpatterns_openid_auth, urlpatterns_service_auth, urlpatterns_auth_management
from visionaire.urls.secure import urlpatterns_api as visionaire_urlpatterns_api

from gateway import gateway_app_name
from gateway.urls import urlpatterns_api as gateway_urlpatterns_api


urlpatterns = [

	# Django Adminh
    path('admin/', admin.site.urls),
]


# Accounts: Login, logout, service authorization
urlpatterns.extend([

    # Visionaire API
    path('visionaire/api/', include((visionaire_urlpatterns_api, visionaire_app_name), namespace='visionaire-api')),

    # Gateway API
    path('gateway/api/', include((gateway_urlpatterns_api, gateway_app_name), namespace='gateway-api')),

    # Content Views: post logout notice. Must stay ahead of the viewer catch-all below, which is
    # wrapped in `login_required` and would send a just-logged-out user back through OpenID login.
    re_path(r'^accounts/logout/success/?$', LogoutSuccessView.as_view(), name='logout-success'),

    # Post logout destination (`post_logout_redirect_uri`). Serves the viewer shell *without*
    # `login_required` so the frontend can render its sign-out confirmation page; the viewer
    # catch-all below would otherwise bounce the just-logged-out user back through OpenID login
    # and sign them straight back in (ohif-viewers#31). The ".html" spelling is canonical (it
    # matches the silent-refresh endpoint and the URI existing viewer builds are configured
    # with); the bare form is accepted as an alias.
    re_path(r'^logout-redirect\.html/?$', OhifSignedOutViewer.as_view(), name='logout-redirect'),
    re_path(r'^logout-redirect/?$', OhifSignedOutViewer.as_view(), name='logout-redirect-alias'),

    # oAuth/OpenID
    path('auth/openid/', include((urlpatterns_openid_auth, visionaire_app_name), namespace='auth')),
	re_path(r'^accounts/login/?$', LoginView.as_view(), name='login'),

    # OpenID Connect RP-Initiated Logout. Published as `end_session_endpoint` in the OpenID
    # configuration document, so it must answer the top level GET that the viewer navigates to.
	re_path(r'^accounts/logout/?$', OpenIDEndSessionView.as_view(), name='logout'),

    # Service Authorization Endpoints; Orthanc
    path('auth/service/', include((urlpatterns_service_auth, visionaire_app_name), namespace='auth-service')),

    # Auth Management Endpoints: Credential/User Management
    path('auth/api/', include((urlpatterns_auth_management, visionaire_app_name), namespace='auth-api')),    
])


urlpatterns.extend([

	# OHIF: Session Renew Endpoint
    re_path(r'^silent-refresh.html$', login_required(oAuth2TokenRefreshView.as_view()), name='silent-refresh'),

    # Sonador Root Configuration
    re_path(r'^ohif/config/?$', OhifConfigView.as_view(content_type=gapicodes.HTTP_CONTENT_TYPE_JSON), name='ohif-config'),

    # OHIF: Imaging Server Specific Configuration and Viewer
    re_path(r'^ohif/config/(?P<iserverid>\w+)/?$',
        OhifConfigView.as_view(content_type=gapicodes.HTTP_CONTENT_TYPE_JSON), name='ohif-imageserver-config'),

    # Sonador Root Viewer
    re_path(r'^.*$', login_required(OhifDicomViewer.as_view()), name='ohif-viewer'),
])


# Development URL patterns
if gsetting('DEBUG'):

    from django.conf.urls.static import static
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    # Static files for development
    if gsetting('STATIC_URL') and os.path.exists(gsetting('STATIC_ROOT')):
        urlpatterns += staticfiles_urlpatterns()        

    # Serve media files from local media path
    if gsetting('MEDIA_URL') and os.path.exists(gsetting('MEDIA_ROOT')):
       urlpatterns.extend(static(gsetting('MEDIA_URL'), document_root=gsetting('MEDIA_ROOT')))