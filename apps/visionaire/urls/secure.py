from django.urls import path, re_path
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

from ..auth.models import DataService, PacsImagingServerGroupAuthorization
from ..auth.views.service import SecureApiLoginView
from ..auth.views.user import UserManagementView, UserRestView, GroupManagementView, GroupRestView
from ..auth.views.service.integrations import DataServiceAuthorizationView
from ..auth.helpers import api_permission_user_readonly_admin_modify, api_permission_imageserver_user_readonly_admin_modify


urlpatterns_api = [

	# API Client Login
	re_path(r'^login/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and (user.is_superuser or user.is_staff),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET',),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			SecureApiLoginView.as_view()), 
		name='api-client-login'),


	# Data Service API
	re_path(r'^data/service/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				allowed_http_methods_url_signature=('GET', 'OPTIONS', 'POST'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'OPTIONS', 'POST'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			SonadorApiObjectManagementView.as_view(model=DataService)), 
		name='data-service-management'),
	re_path(r'^data/service/(?P<objectid>[a-zA-Z0-9]+)/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'PATCH', 'PUT', 'DELETE'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			DataServiceApiRestView.as_view()), 
		name='data-service-update'),
	re_path(r'^data/service/(?P<objectid>[a-zA-Z0-9]+)/introspect/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				allowed_http_methods_url_signature=('POST',),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('POST',), allow_formencoded=True,
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			DataServiceAuthorizationView.as_view()), 
		name='data-service-token-introspect'),

	
	# Image Server API
	re_path(r'^pacs/?$', 
		api_request(api_permission_user_readonly_admin_modify,
				allowed_http_methods_url_signature=('GET', 'OPTIONS', 'POST'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'OPTIONS', 'POST'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerApiManagementView.as_view()), 
		name='pacs-server-management'),
	re_path(r'^pacs/(?P<objectid>[a-zA-Z0-9]+)/?$', 
		api_request(api_permission_imageserver_user_readonly_admin_modify,
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'PATCH', 'PUT', 'DELETE'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerApiRestView.as_view()), 
		name='pacs-server-update'),

	# Image Server API: PACS DICOM Modalities
	re_path(r'^pacs/(?P<serverid>[a-zA-Z0-9]+)/dicom/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				allowed_http_methods_url_signature=('GET', 'OPTIONS', 'POST'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'OPTIONS', 'POST'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectManagementView.as_view(model=DicomImagingModality)), 
		name='pacs-server-modality-management'),
	re_path(r'^pacs/(?P<serverid>[a-zA-Z0-9]+)/dicom/(?P<objectid>[a-zA-Z0-9]+)/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'PATCH', 'PUT', 'DELETE'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectRestView.as_view(model=DicomImagingModality)), 
		name='pacs-server-modality-update'),

	# Image Server API: PACS DICOMweb Peers
	re_path(r'^pacs/(?P<serverid>[a-zA-Z0-9]+)/dicom-web/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				allowed_http_methods_url_signature=('GET', 'OPTIONS'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'OPTIONS', 'POST'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectManagementView.as_view(model=RemoteDICOMwebServer)), 
		name='pacs-server-dicomweb-management'),
	re_path(r'^pacs/(?P<serverid>[a-zA-Z0-9]+)/dicom-web/(?P<objectid>[a-zA-Z0-9]+)/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'PATCH', 'PUT', 'DELETE'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectRestView.as_view(model=RemoteDICOMwebServer)), 
		name='pacs-server-dicomweb-update'),

	# Imaging Server API: Group Access Control Management
	re_path("^pacs/(?P<serverid>[a-zA-Z0-9]+)/acl/?$",
		api_request(lambda user, request, vargs, vkwags: user.is_authenticated and user.is_superuser,
				apiaccess_token_model=ApiAccessToken,
				allowed_http_methods_token_access=('GET', "POST"),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectManagementView.as_view(model=PacsImagingServerGroupAuthorization)),
		name="group-access-control-management",
	),
	re_path("^pacs/(?P<serverid>[a-zA-Z0-9]+)/acl/(?P<objectid>[a-zA-Z0-9]+)/?$",
		api_request(lambda user, request, vargs, vkwags: user.is_authenticated and user.is_superuser,
				apiaccess_token_model=ApiAccessToken,
				allowed_http_methods_token_access=("GET", "PATCH", "PUT", "DELETE"),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectRestView.as_view(model=PacsImagingServerGroupAuthorization)),
		name="group-access-control-update",
	),


	# User Management API
	path("user", api_request(lambda user, request, vargs, vkwags: user.is_authenticated and user.is_superuser,
				apiaccess_token_model=ApiAccessToken,
				allowed_http_methods_token_access=("GET", "POST",),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			UserManagementView.as_view()),
		name="user-management",
	),
	path("user/<int:objectid>",
		api_request(lambda user, request, vargs, vkwags: user.is_authenticated and user.is_superuser,
				apiaccess_token_model=ApiAccessToken,
				allowed_http_methods_token_access=("GET", "PATCH", "PUT", "DELETE"),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			UserRestView.as_view()),
		name="user-update",
	),

	
	# Group Management API
	path("group", api_request(lambda user, request, vargs, vkwags: user.is_authenticated and user.is_superuser,
				apiaccess_token_model=ApiAccessToken,
				allowed_http_methods_token_access=("GET", "POST",),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			GroupManagementView.as_view()),
		name="group-management",
	),
	path("group/<int:objectid>",
		api_request(lambda user, request, vargs, vkwags: user.is_authenticated and user.is_superuser,
				apiaccess_token_model=ApiAccessToken,
				allowed_http_methods_token_access=("GET", "PATCH", "PUT", "DELETE"),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			GroupRestView.as_view()),
		name="group-update",
	),
]
