import os

from django.urls import include
from django.urls import path, re_path
from django.conf.urls.static import static
from django.views.generic.base import TemplateView

from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views

from guru.helpers import gsetting
from guru import apisettings as gapicodes

from visionaire import visionaire_app_name
from visionaire.auth.views import LoginView, oAuth2TokenAuthorizationView, oAuth2TokenRefreshView
from visionaire.auth.views.service import OrthancSecureUriRedirectView
from visionaire.views import OhifConfigView, OhifDicomViewer
from visionaire.auth.urls import urlpatterns_openid_auth, urlpatterns_service_auth, urlpatterns_auth_management
from visionaire.urls.secure import urlpatterns_api as visionaire_urlpatterns_api

from gateway import gateway_app_name
from gateway.urls import urlpatterns_api as gateway_urlpatterns_api


urlpatterns = [

	# Django Adminh
    path('admin/', admin.site.urls),
]


# Development URL patterns
if gsetting('DEBUG') and gsetting('MEDIA_URL') and os.path.exists(gsetting('MEDIA_ROOT')):
	urlpatterns.extend(static(gsetting('MEDIA_URL'), document_root=gsetting('MEDIA_ROOT')))

# Accounts: Login, logout, service authorization
urlpatterns.extend([

    # Visionaire API
    path('visionaire/api/', include((visionaire_urlpatterns_api, visionaire_app_name), namespace='visionaire-api')),

    # Gateway API
    path('gateway/api/', include((gateway_urlpatterns_api, gateway_app_name), namespace='gateway-api')),

    # Content Views
    re_path(r'^accounts/logout/success/?$', 
        TemplateView.as_view(template_name='content/logout.html'), name='logout-success'),
    
    # oAuth/OpenID
    path('auth/openid/', include((urlpatterns_openid_auth, visionaire_app_name), namespace='auth')),
	re_path(r'^accounts/login/?$', LoginView.as_view(), name='login'),
	re_path(r'^accounts/logout/?$', auth_views.LogoutView.as_view(), name='logout'),

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
    re_path(r'^ohif/viewer/(?P<iserverid>\w+)/?(.+)?/?$', 
        login_required(OhifDicomViewer.as_view()) if gsetting('AUTH_ENABLED') else OhifDicomViewer.as_view(),
        name='ohif-imageserver-viewer'),

    # Sonador Root Viewer
    re_path(r'^.*$', 
    	login_required(OhifDicomViewer.as_view()) if gsetting('AUTH_ENABLED') else OhifDicomViewer.as_view(),
    	name='ohif-viewer'),
])
