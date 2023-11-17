from django.urls import path, re_path

from secure.helpers import api_request
from secure.models import ApiAccessToken

from visionaire.helpers import API_ACCESS_APITOKEN_QSPARAM
from visionaire.auth.helpers import api_permission_user_readonly_admin_modify
from visionaire.views.dicom import PacsImagingServerChildObjectManagementView, PacsImagingServerChildObjectRestView

from .views import ClinicalGatewayApiManagementView, ClinicalGatewayApiRestView
from .helpers import api_permission_admin_device_owner
from .models import ClinicalGateway, GatewayDicomImagingModality, GatewayImagingServer, ClinicalGatewayVariable


urlpatterns_api = [

	# Device APIs
	re_path(r'^device/?$', 
		api_request(lambda user, request, vargs, vkwargs: user.is_authenticated,
				allowed_http_methods_url_signature=('GET', 'OPTIONS', 'POST'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'OPTIONS', 'POST'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			ClinicalGatewayApiManagementView.as_view()), 
		name='gateway-management'),
	re_path(r'^device/(?P<objectid>[a-zA-Z0-9]+)/?$', 
		api_request(api_permission_admin_device_owner,
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'PATCH', 'PUT', 'DELETE'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			ClinicalGatewayApiRestView.as_view()), 
		name='gateway-update'),

	# Device API: Local Network DICOM Modalities
	re_path(r'^device/(?P<gatewayid>[a-zA-Z0-9]+)/dicom/?$', 
		api_request(
				lambda user, request, vargs, vkwargs: api_permission_admin_device_owner(
					user, request, vargs, vkwargs, device_url_param='gatewayid'),
				allowed_http_methods_url_signature=('GET', 'OPTIONS', 'POST'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'OPTIONS', 'POST'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectManagementView.as_view(
				parent_model=ClinicalGateway, model=GatewayDicomImagingModality,
				parent_fieldname='gateway', request_parent_fieldname='gatewayid')), 
		name='gateway-modality-management'),
	re_path(r'^device/(?P<gatewayid>[a-zA-Z0-9]+)/dicom/(?P<objectid>[a-zA-Z0-9]+)/?$', 
		api_request(
				lambda user, request, vargs, vkwargs: api_permission_admin_device_owner(
					user, request, vargs, vkwargs, device_url_param='gatewayid'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'PATCH', 'PUT', 'DELETE'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectRestView.as_view(
				parent_model=ClinicalGateway, model=GatewayDicomImagingModality, 
				parent_fieldname='gateway', request_parent_fieldname='gatewayid')), 
		name='gateway-modality-update'),

	# Device API: Imaging Servers Attached to the Gateway
	re_path(r'^device/(?P<gatewayid>[a-zA-Z0-9]+)/dicom-web/?$', 
		api_request(
				lambda user, request, vargs, vkwargs: api_permission_admin_device_owner(
					user, request, vargs, vkwargs, device_url_param='gatewayid'),
				allowed_http_methods_url_signature=('GET', 'OPTIONS', 'POST'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'OPTIONS', 'POST'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectManagementView.as_view(
				parent_model=ClinicalGateway, model=GatewayImagingServer,
				parent_fieldname='gateway', request_parent_fieldname='gatewayid')), 
		name='gateway-pacs-management'),
	re_path(r'^device/(?P<gatewayid>[a-zA-Z0-9]+)/dicom-web/(?P<objectid>[a-zA-Z0-9]+)/?$', 
		api_request(
				lambda user, request, vargs, vkwargs: api_permission_admin_device_owner(
					user, request, vargs, vkwargs, device_url_param='gatewayid'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'PATCH', 'PUT', 'DELETE'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectRestView.as_view(
				parent_model=ClinicalGateway, model=GatewayImagingServer, 
				parent_fieldname='gateway', request_parent_fieldname='gatewayid')), 
		name='gateway-pacs-update'),

	# Device API: Gateway Environment
	re_path(r'^device/(?P<gatewayid>[a-zA-Z0-9]+)/env/?$', 
		api_request(
				lambda user, request, vargs, vkwargs: api_permission_admin_device_owner(
					user, request, vargs, vkwargs, device_url_param='gatewayid'),
				allowed_http_methods_url_signature=('GET', 'OPTIONS', 'POST'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'OPTIONS', 'POST'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectManagementView.as_view(
				parent_model=ClinicalGateway, model=ClinicalGatewayVariable,
				parent_fieldname='gateway', request_parent_fieldname='gatewayid')), 
		name='env-management'),
	re_path(r'^device/(?P<gatewayid>[a-zA-Z0-9]+)/env/(?P<objectid>[a-zA-Z0-9]+)/?$', 
		api_request(
				lambda user, request, vargs, vkwargs: api_permission_admin_device_owner(
					user, request, vargs, vkwargs, device_url_param='gatewayid'),
				apiaccess_token_model=ApiAccessToken, allowed_http_methods_token_access=('GET', 'PATCH', 'PUT', 'DELETE'),
				request_header_accesstoken=API_ACCESS_APITOKEN_QSPARAM)(
			PacsImagingServerChildObjectRestView.as_view(
				parent_model=ClinicalGateway, model=ClinicalGatewayVariable, 
				parent_fieldname='gateway', request_parent_fieldname='gatewayid')), 
		name='env-update'),
]