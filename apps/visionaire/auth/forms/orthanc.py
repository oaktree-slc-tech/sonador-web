import logging, six, copy, base64
from six.moves.urllib import parse as urlparse

from django import forms
from django.core import signing
from django.shortcuts import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import View, RedirectView

from django.contrib import auth
from django.contrib.sessions.backends.db import SessionStore

from guru.errors import OperationError
from guru.helpers import gsetting, operation_results
from guru.helpers.compatability import guru_page_not_found, guru_permission_denied
from guru.helpers.urls import merge_url_querystring
from guru.helpers.utils.object import pick, omit

from secure.models import ApiAccess, ApiAccessToken
from secure.helpers import server_decrypt_data

from wgtauth.apisettings import BASIC_AUTH_TYPE, \
	OAUTH_ACCESS_TOKEN, OAUTH_TOKEN_TYPE, OAUTH_TOKEN_TYPE_BEARER, OAUTH_EXPIRATION, \
	OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE
from wgtauth.forms import oAuthTokenAuthorizationForm

from orthancapi import apisettings as orthanc_api

from ...views.base import JSONFormApiView
from ...helpers import SESSION_SALT, ACCESS_TOKEN_MAX_AGE, \
	API_ACCESS_SERVER_TOKEN, API_ACCESS_TOKEN_QSPARAM, API_ACCESS_APITOKEN_QSPARAM, \
	API_REFERRER_REFERER_HEADER
from ...models import PacsImagingServer

from .. import hexsigning

from .base import ServiceAuthorizationRequest, SonadorServiceAuthorizationBaseForm

from .credential_providers.sonador import SonadorCredentialProvider
from .credential_providers.staticfile import SonadorStaticFileCredentialProvider
from .credential_providers.cache import SonadorTokenCacheCredentialProvider
from .credential_providers.remote import SonadorRemoteCredentialProvider

from .integrations import IntegrationAuthorizationForm

logger = logging.getLogger(__name__)


class ImagingServerFormMixin:
	'''	Mixin class which provides methods for validating access to imaging server instances
	'''
	def _init_server(self, *args, **kwargs):
		'''	Initialize imaging server properties for the form
		'''
		self.server = kwargs.pop("server", None)

		if not self.server:
			raise ValueError("Unable to initialize authorization form: imaging server not provided")


class ImagingServerIntegrationAuthorizationForm(ImagingServerFormMixin, IntegrationAuthorizationForm):
	'''	Form class wich can be used to introspect requests associated with an imaging server instance.
		For  authorization of requests sent by the Orthanc advanced authorization plugin, 
		use OrthancServiceAuthorizationForm.
	'''
	def __init__(self, *args, **kwargs):
		self._init_server(*args, **kwargs)
		super().__init__(*args, **omit(kwargs, ('server',)))

	def clean(self, *args, **kwargs):
		'''	Ensure that the user has access to the server before authorizing the request
		'''
		cleaned_data = super().clean(*args, *kwargs)

		if not getattr(self, 'user', None):
			raise forms.ValidationError('Unable to retrieve valid user instance for token')
		if getattr(self, 'user', None) and self.user.pk and not self.server.user_has_access(self.user):
			raise forms.ValidationError('User "%s" does not have permission to access data server "%s"' % (
					self.user, self.server.pk
				))

		return cleaned_data


class OrthancServiceAuthorizationForm(ImagingServerFormMixin, SonadorServiceAuthorizationBaseForm):
	'''	Form class which can be used to approve or deny authorization requests from Orthanc. This form provides
		authorization for static file and secure resources, and is able to validate credentials from remote IdP instances.
		It implements the API defined by the Orthanc Advanced Authorization Plugin "token introspection" endpoint:
		https://orthanc.uclouvain.be/book/plugins/authorization.html#get-user-profile-user-get-profile
	'''
	level = forms.CharField(required=False)
	method = forms.CharField(required=False)

	dicom_uid = forms.CharField(required=False)
	orthanc_id = forms.CharField(required=False)
	uri = forms.CharField(required=False)

	formdata_transforms = {
		'token-key': 'token_key',
		'token-value': 'token_value',
		'orthanc-id': 'orthanc_id',
		'dicom-uid': 'dicom_uid',
	}

	credential_providers = [
		SonadorStaticFileCredentialProvider, SonadorCredentialProvider, 
		SonadorTokenCacheCredentialProvider, SonadorRemoteCredentialProvider
	]

	def __init__(self, *args, **kwargs):
		self._init_server(*args, **kwargs)		
		super().__init__(*args, **omit(kwargs, ('server',)))

	def clean(self, *args, **kwargs):
		'''	Clean data and convert parameters to the format required needed for session
			or API token authorization.
		'''
		cleaned_data = super(OrthancServiceAuthorizationForm, self).clean(*args, **kwargs)
		logger.debug('Authentication request data:\n%r' % cleaned_data)

		# Parse authentication from "Referrer" headers
		if cleaned_data.get('token_key') == API_REFERRER_REFERER_HEADER:

			# Retrieve querystring components
			rparts = urlparse.parse_qs(urlparse.urlparse(cleaned_data.get('token_value', '')).query) \
					if getattr(urlparse.urlparse(cleaned_data.get('token_value', '')), 'query', None) \
				else {}

			logger.debug('Querystring parameters from referrer URL: %r' % rparts)

			# Iterate through querystring components and re-package to remove single list values
			for k,v in six.iteritems(rparts):
				if isinstance(v, (tuple, list)) and len(v) == 1:
					rval = v[0]

					# For session based tokens add "Bearer" to the string
					if ':' in rval:
						rval = '%s %s' % (OAUTH_TOKEN_TYPE_BEARER, rval)

					rparts[k] = rval

				# Check component for API tokens or session keys
				if k in (API_ACCESS_APITOKEN_QSPARAM, API_ACCESS_TOKEN_QSPARAM):
					cleaned_data['referrer_token_key'] = k
					cleaned_data['referrer_token_value'] = rparts.get(k)
					logger.debug('Token value in referrer URL: %s' % cleaned_data['referrer_token_value'])

		# Signed session key passed as "token", add "Bearer" keyword to the token value
		elif cleaned_data.get('token_key') == API_ACCESS_TOKEN_QSPARAM and ':' in cleaned_data.get('token_value', ''):
			cleaned_data['token_value'] = '%s %s' % (OAUTH_TOKEN_TYPE_BEARER, cleaned_data.get('token_value', ''))

		# Parse authentication data
		cleaned_data = self.clean_authdata(cleaned_data)
		cleaned_data = self.clean_auth_request(cleaned_data)
		return cleaned_data

	def _clean_dcmweb_resource_level(self, cleaned_data, dcmweb_regex):
		''' Use the provided DICOMweb regular expression patter to to normalize the resource level
		'''
		# Parse resource type and UID from URL
		if dcmweb_regex and dcmweb_regex.group('uid') \
			and (dcmweb_regex.group('resource_type') in orthanc_api.ORTHANC_LOCALAUTH_RESOURCES 
				or dcmweb_regex.group('resource_type') in orthanc_api.ORTHANC_LOCALAUTH_RESOURCES_PLURAL):

			# Convert matched resource to type to corresponding level code in Orthanc API. If the resource type is the 
			# plural form of the level, convert to singular before processing the ACL request
			cleaned_data['level'] = orthanc_api.ORTHANC_LOCALAUTH_RESOURCES_PLURAL.get(dcmweb_regex.group('resource_type')) \
					if dcmweb_regex.group('resource_type') in orthanc_api.ORTHANC_LOCALAUTH_RESOURCES_PLURAL \
				else dcmweb_regex.group('resource_type')				

			# DICOM UID parsed from URL
			cleaned_data['dicom_uid'] = dcmweb_regex.group('uid')

		return cleaned_data

	def clean_auth_request(self, cleaned_data):
		'''	Apply transforms to the advanced authorization data to ensure that requests are processed correctly.

			1.	Detect DICOMweb requests incorrectly classified as system requests.
			2.	Parse resource components, such as UIDs, from URLs and back-fill when needed.
			3.	Detect gorup and other Sonador <-> Orthanc integration API calls, such as the tags API
				and parse to components.
		'''
		resource = cleaned_data.get('resource')
		uri = cleaned_data.get('uri')
		level = cleaned_data.get('level')
		orthanc_id = cleaned_data.get('orthanc_id')
		dicom_uid = cleaned_data.get('dicom_uid')

		# The requested resource might be provided by the Orthanc advanced authorization
		# plugin as a UID or a URL. Transforming system requests requries looking at both fields.
		_resource = resource or uri or ''

		# Check for DICOMweb worklist request
		if orthanc_api.ORTHANC_DICOMWEB in _resource and orthanc_api.ORTHANC_RESOURCE_WORKLIST in _resource:

			# Parse DICOM UID from resource URI
			_worklist_study = orthanc_api.ORTHANC_DICOMWEB_WORKLIST_MANAGEMENT_REGEX.match(_resource)

			if _worklist_study and _worklist_study.group('uid'):
				cleaned_data['level'] = orthanc_api.ORTHANC_RESOURCE_STUDY
				cleaned_data['dicom_uid'] = _worklist_study.group('uid')

		# Check for DICOMweb study or series archive download
		if orthanc_api.ORTHANC_DICOMWEB in _resource and orthanc_api.ORTHANC_RESOURCE_ARCHIVE in _resource:

			# Parse DICOM UID and resource level from URI
			_dcmweb_archive = orthanc_api.ORTHANC_DICOMWEB_DOWNLOAD_REGEX.match(_resource)
			cleaned_data = self._clean_dcmweb_resource_level(cleaned_data, _dcmweb_archive)

		# Check for DICOMweb study comment request
		elif orthanc_api.ORTHANC_DICOMWEB in _resource and orthanc_api.ORTHANC_RESOURCE_COMMENT in _resource:

			# Parse DICOM UID and resource level from URI
			_dcmweb_comment = orthanc_api.ORTHANC_DICOMWEB_COMMENT_REGEX.match(_resource)
			cleaned_data = self._clean_dcmweb_resource_level(cleaned_data, _dcmweb_comment)

		# Check for DICOMweb ACL lookup (resource permissions)
		elif orthanc_api.ORTHANC_DICOMWEB in _resource and orthanc_api.ORTHANC_DICOMWEB_RESOURCE_ACL in _resource:

			# Parse DICOM UID and resource level from URI
			_dcmweb_resource_perms = orthanc_api.ORTHANC_DICOMWEB_ACL_PERMS_REGEX.match(_resource)
			cleaned_data = self._clean_dcmweb_resource_level(cleaned_data, _dcmweb_resource_perms)

		# Check for DICOMweb series distortion filter
		elif orthanc_api.ORTHANC_DICOMWEB_GROUPS_ROOT in _resource:
			
			# Parse DICOMM UID and resource level
			_dcmweb_distortion_filter = orthanc_api.ORTHANC_DICOMWEB_DISTORTION_FILTER_REGEX.match(_resource)

			if _dcmweb_distortion_filter and _dcmweb_distortion_filter.group('uid'):
				cleaned_data['level'] = orthanc_api.ORTHANC_RESOURCE_STUDY
				cleaned_data['dicom_uid'] = _dcmweb_distortion_filter.group('uid')
				cleaned_data['group'] = int(_dcmweb_distortion_filter.group('group_uid'))

		# Orthanc / Sonador Integration APIs: Group Owned Resources
		elif orthanc_api.ORTHANC_GROUPS_ROOT in _resource and not orthanc_id:

			# Group tags or distortion filter request
			_group_resource = orthanc_api.ORTHANC_GROUP_UID_REGEX.match(_resource)			
			if _group_resource:
				cleaned_data['level'] = orthanc_api.ORTHANC_RESOURCE_GROUP
				cleaned_data['orthanc_id'] = int(_group_resource.group('uid'))

		# Check for Orthanc Internal DICOMweb endpoint requests
		elif orthanc_api.ORTHANC_DICOMWEB_INTERNAL in _resource:

			# DICOMweb series metadata requests
			if _dcmweb_series_meta := orthanc_api.ORTHANC_DICOMWEB_INTERNAL_SERIES_METADATA_REGEX.match(_resource):			
				cleaned_data = self._clean_dcmweb_resource_level(cleaned_data, _dcmweb_series_meta)

			# DICOMweb instance requests
			elif _dcmweb_instance := orthanc_api.ORTHANC_DICOMWEB_INTERNAL_INSTANCE_REGEX.match(_resource):
				cleaned_data = self._clean_dcmweb_resource_level(cleaned_data, _dcmweb_instance)

			# DICOMweb instance / frame requests
			elif _dcmweb_instance_frameimage := orthanc_api.ORTHANC_DICOMWEB_INTERNAL_INSTANCE_FRAME_REGEX.match(_resource):
				cleaned_data = self._clean_dcmweb_resource_level(cleaned_data, _dcmweb_instance_frameimage)
						
		return cleaned_data


class OrthancServiceResourceAuthorizationForm(OrthancServiceAuthorizationForm):
	'''	Specialized form of OrthancServiceAuthorizationForm which enforces resource level and orthanc-uid
		as required fields.
	'''
	def clean(self, *args, **kwargs):
		cleaned_data = super().clean(*args, **kwargs)

		# Ensure that a resource level was provided with the request
		if not cleaned_data.get('level'):
			raise forms.ValidationError('Resouce requests require a resource level in order to be valid.')

		# Ensure that an Orthanc or DICOM UID was provided to identify the resource
		if not cleaned_data.get('orthanc_id') and not cleaned_data.get('dicom_uid'):
			raise forms.ValidationError('Invalid resource UID. Resource requests require that either an Orthanc UID or DICOM UID be '
				+ 'provided with the request.')

		return cleaned_data