from django.urls import path, re_path
from django.conf.urls import url, include

from guru.views import GuruApiObjectManagementView, GuruApiRestView

from secure.models import ApiAccessToken
from secure.helpers import api_request

from ..models.servers import PacsImagingServer
from ..models.dicom import DicomImagingModality, RemoteDICOMwebServer
from ..views.base import SonadorApiObjectManagementView, SonadorApiRestView
from ..views.dicom import PacsImagingServerChildObjectManagementView, PacsImagingServerChildObjectRestView
from ..auth.views.service import SecureApiLoginView
from ..helpers import API_ACCESS_APITOKEN_QSPARAM


urlpatterns_api = [

	# API Client Login
	url(r'^login/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and (user.is_superuser or user.is_staff),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET',),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			SecureApiLoginView.as_view()), 
		name='api-client-login'),

	# Image Server API endpoints
	url(r'^pacs/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and (user.is_superuser or user.is_staff),
				allowed_http_methods_url_signature=('GET', 'OPTIONS'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'OPTIONS', 'POST'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			SonadorApiObjectManagementView.as_view(model=PacsImagingServer)), 
		name='pacs-server-management'),
	url(r'^pacs/(?P<objectid>[a-zA-Z0-9]+)/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and (user.is_superuser or user.is_staff),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'PATCH', 'PUT', 'DELETE'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			SonadorApiRestView.as_view(model=PacsImagingServer)), 
		name='pacs-server-update'),

	# Image Server API: PACS DICOM Modalities
	url(r'^pacs/(?P<serverid>[a-zA-Z0-9]+)/dicom/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				allowed_http_methods_url_signature=('GET', 'OPTIONS'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'OPTIONS', 'POST'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectManagementView.as_view(model=DicomImagingModality)), 
		name='pacs-server-modality-management'),
	url(r'^pacs/(?P<serverid>[a-zA-Z0-9]+)/dicom/(?P<objectid>[a-zA-Z0-9]+)/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'PATCH', 'PUT', 'DELETE'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectRestView.as_view(model=DicomImagingModality)), 
		name='pacs-server-modality-management'),

	# Image Server API: PACS DICOM Modalities
	url(r'^pacs/(?P<serverid>[a-zA-Z0-9]+)/dicom-web/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				allowed_http_methods_url_signature=('GET', 'OPTIONS'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'OPTIONS', 'POST'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectManagementView.as_view(model=RemoteDICOMwebServer)), 
		name='pacs-server-modality-management'),
	url(r'^pacs/(?P<serverid>[a-zA-Z0-9]+)/dicom-web/(?P<objectid>[a-zA-Z0-9]+)/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated and user.is_superuser,
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'PATCH', 'PUT', 'DELETE'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectRestView.as_view(model=RemoteDICOMwebServer)), 
		name='pacs-server-modality-management'),
]

