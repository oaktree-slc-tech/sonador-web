from django.urls import path, re_path
from django.conf.urls import url, include

from guru.views import GuruApiObjectManagementView, GuruApiRestView

from secure.models import ApiAccessToken
from secure.helpers import api_request

from ..helpers import API_ACCESS_APITOKEN_QSPARAM
from ..models.servers import PacsImagingServer
from ..models.dicom import DicomImagingModality, RemoteDICOMwebServer

from ..views.base import SonadorApiObjectManagementView, SonadorApiRestView
from ..views.dicom import PacsImagingServerChildObjectManagementView, PacsImagingServerChildObjectRestView
from ..views.servers import PacsImagingServerApiManagementView, PacsImagingServerApiRestView
from ..views.integrations import DataServiceApiRestView

from ..auth.models import DataService
from ..auth.views.service import SecureApiLoginView
from ..auth.views.service.integrations import DataServiceAuthorizationView
from ..auth.helpers import api_permission_user_readonly_admin_modify


urlpatterns_api = [

	# API Client Login
	url(r'^login/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and (user.is_superuser or user.is_staff),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET',),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			SecureApiLoginView.as_view()), 
		name='api-client-login'),


	# Data Service API
	url(r'^data/service/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				allowed_http_methods_url_signature=('GET', 'OPTIONS', 'POST'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'OPTIONS', 'POST'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			SonadorApiObjectManagementView.as_view(model=DataService)), 
		name='data-service-management'),
	url(r'^data/service/(?P<objectid>[a-zA-Z0-9]+)/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'PATCH', 'PUT', 'DELETE'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			DataServiceApiRestView.as_view()), 
		name='data-service-update'),
	url(r'^data/service/(?P<objectid>[a-zA-Z0-9]+)/introspect/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				allowed_http_methods_url_signature=('POST',),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('POST',),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			DataServiceAuthorizationView.as_view()), 
		name='data-service-token-introspect'),

	
	# Image Server API
	url(r'^pacs/?$', 
		api_request(api_permission_user_readonly_admin_modify,
				allowed_http_methods_url_signature=('GET', 'OPTIONS', 'POST'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'OPTIONS', 'POST'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerApiManagementView.as_view()), 
		name='pacs-server-management'),
	url(r'^pacs/(?P<objectid>[a-zA-Z0-9]+)/?$', 
		api_request(api_permission_user_readonly_admin_modify,
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'PATCH', 'PUT', 'DELETE'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerApiRestView.as_view()), 
		name='pacs-server-update'),

	# Image Server API: PACS DICOM Modalities
	url(r'^pacs/(?P<serverid>[a-zA-Z0-9]+)/dicom/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				allowed_http_methods_url_signature=('GET', 'OPTIONS', 'POST'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'OPTIONS', 'POST'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectManagementView.as_view(model=DicomImagingModality)), 
		name='pacs-server-modality-management'),
	url(r'^pacs/(?P<serverid>[a-zA-Z0-9]+)/dicom/(?P<objectid>[a-zA-Z0-9]+)/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'PATCH', 'PUT', 'DELETE'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectRestView.as_view(model=DicomImagingModality)), 
		name='pacs-server-modality-update'),

	# Image Server API: PACS DICOMweb Peers
	url(r'^pacs/(?P<serverid>[a-zA-Z0-9]+)/dicom-web/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				allowed_http_methods_url_signature=('GET', 'OPTIONS'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'OPTIONS', 'POST'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectManagementView.as_view(model=RemoteDICOMwebServer)), 
		name='pacs-server-dicomweb-management'),
	url(r'^pacs/(?P<serverid>[a-zA-Z0-9]+)/dicom-web/(?P<objectid>[a-zA-Z0-9]+)/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'PATCH', 'PUT', 'DELETE'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectRestView.as_view(model=RemoteDICOMwebServer)), 
		name='pacs-server-dicomweb-update'),
]

