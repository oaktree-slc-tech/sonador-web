import os

from django.urls import path, re_path
from django.conf.urls import url, include
from django.conf.urls.static import static
from django.views.generic.base import TemplateView

from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views

from guru.helpers import gsetting

from visionaire import visionaire_app_name
from visionaire.auth.views import LoginView
from visionaire.auth.views.service import OrthancSecureUriRedirectView
from visionaire.views import OhifDicomViewer
from visionaire.auth.urls import urlpatterns_openid_auth, urlpatterns_service_auth


urlpatterns = [

	# Django Adminh
    path('admin/', admin.site.urls),
]


# Development URL patterns
if gsetting('DEBUG') and gsetting('MEDIA_URL') and os.path.exists(gsetting('MEDIA_ROOT')):
	urlpatterns.extend(static(gsetting('MEDIA_URL'), document_root=gsetting('MEDIA_ROOT')))

# Login/logout
if gsetting('AUTH_ENABLED'):
	urlpatterns.extend([

        # Content Views
        url(r'^accounts/logout/success/?$', 
            TemplateView.as_view(template_name='content/logout.html'), name='logout-success'),
        
        # oAuth/OpenID
        url(r'^auth/openid/', include((urlpatterns_openid_auth, visionaire_app_name), namespace='auth')),
		url(r'^accounts/login/?$', LoginView.as_view(), name='login'),
    	url(r'^accounts/logout/?$', auth_views.LogoutView.as_view(), name='logout'),

        # Service Authorization Endpoints; Orthanc
        url(r'^auth/service/', include((urlpatterns_service_auth, visionaire_app_name), namespace='auth-service')),
	])


urlpatterns.extend([

	# OHIF
    re_path(r'^.*$', 
    	login_required(OhifDicomViewer.as_view()) if gsetting('AUTH_ENABLED') else OhifDicomViewer.as_view(),
    	name='ohif-viewer'),
])
