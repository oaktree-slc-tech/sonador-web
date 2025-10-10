'''	Orthanc Service Token Authorization View: primary view instances used to authorization access
	to Orthanc resources.
'''
import logging, posixpath, json
from blake3 import blake3

from django.core.cache import cache

from guru import apisettings as gapi
from guru.errors import OperationError, GuruFormError
from guru.forms.helpers import validate_form_data
from guru.helpers import gsetting, create_token, operation_results
from guru.helpers.utils.object import omit

from secure.models import ApiAccess, ApiAccessToken
from secure.helpers import server_decrypt_data, masked_value

from orthancapi import apisettings as orthanc_api
from orthancapi.helpers import orthanc_hosted_staticfile

from ....apisettings import SONADOR_USERNAME
from ...forms.orthanc import OrthancServiceAuthorizationForm
from .base import SonadorServiceAuthorizationBaseView, OrthancServiceImagingServerMixin

logger = logging.getLogger(__name__)


class OrthancServiceAuthorizationView(OrthancServiceImagingServerMixin, SonadorServiceAuthorizationBaseView):
	'''	API view which can be used to process authorization requests from Orthanc
	'''
	formclass = OrthancServiceAuthorizationForm
	auth_response_cache_key_template = orthanc_api.ORTHANC_CREDENTIAL_CACHE_KEY_TEMPLATE
	auth_response_cache_prefix = 'orthanc-acl'
	auth_response_cache_sep = '|'
	auth_response_encoding = 'utf-8'
	
	def get_form_kwargs(self, *args, **kwargs):
		form_kwargs = super().get_form_kwargs(*args, **kwargs)
		form_kwargs['server'] = self.getImagingServer(*args, **kwargs)
		return form_kwargs

	def get_auth_request_params(self, *args, form_data=None, **kwargs):
		'''	Retrieve authorization request components
		'''
		_form = getattr(self, 'None', None)
		form_data = form_data or getattr(_form, 'data', {})

		# Request components
		_user = getattr(_form, 'user', None)		
		_orthanc_id = form_data.get('orthanc_id') or ''		
		_level = form_data.get('level') or ''
		_method = form_data.get('method') or ''
		_resource = form_data.get('uri') or ''
		_,_rtype = posixpath.splitext(_resource)

		return _user, _orthanc_id, _level, _method, _resource, _rtype

	def cache_auth_response_key(self, *args, form_data=None, **kwargs):
		'''	Retrieve the hashed cache key for the authorization response
		'''
		# Retrieve request components
		form_data = form_data or self.getRequestJsonData(self.request)
		_, orthanc_id, level, method, resource, _ = self.get_auth_request_params(form_data=form_data, **kwargs)
		_components = self.auth_response_cache_sep.join(str(_c) for _c in (orthanc_id, level, method, resource) if _c)

		# Generate hash key
		return self.auth_response_cache_key_template % (
			(gsetting('SECRET_KEY') or create_token()).encode(self.auth_response_encoding),
			('%s%s%s' % (form_data.get('token_key') or create_token(), self.auth_response_cache_sep, 
				form_data.get('token_value') or create_token())).encode(self.auth_response_encoding),
			self.auth_response_cache_prefix.encode(self.auth_response_encoding),
			_components.encode(self.auth_response_encoding))

	def cache_get_authorization_response(self, request, *args, **kwargs):
		''' Retrieve an authorization response from the system cache
		'''
		_cache_key = self.cache_auth_response_key(*args, **kwargs)
		_cache_key_digest = blake3(_cache_key).hexdigest()
		_cache_response = cache.get(_cache_key_digest)

		logger.debug('Response retrieved from cache: view="%s" cache-key="%s" digest="%s"": "%s"' % (
			self.auth_response_cache_prefix, _cache_key, _cache_key_digest,  _cache_response or ''
		))
		return _cache_key, json.loads(_cache_response) if _cache_response else None

	def cache_set_authorization_response(self, authorization_response, *args, **kwargs):
		'''	Cache an authorization response from the system cache
		'''
		if authorization_response.get('granted'):

			_cache_key = self.cache_auth_response_key(*args, form_data=self.form.cleaned_data, **kwargs)
			_cache_key_digest = blake3(_cache_key).hexdigest()
			cache.set(_cache_key_digest, json.dumps(authorization_response),
				authorization_response.get('granted') or self.form.expires_in)

			_test = cache.get(_cache_key_digest)

			logger.debug('Auth response cached. view="%s" cache-key="%s" digest="%s" response="%s" valid="%s"' % (
				self.auth_response_cache_prefix, _cache_key, _cache_key_digest, authorization_response, 
				authorization_response.get('validity') or self.form.expires_in,
			))

	def get_authorization_response(self, adata, *args, **kwargs):
		'''	Parse the authorization request and create the authorization response
		'''
		# Auth request components
		_user, _orthanc_id, _level, _method, _resource, _rtype = self.get_auth_request_params(
			form_data=self.form.cleaned_data if self.form.is_valid() else self.form.data)

		# Allow requests for static assets
		if self.form.is_valid() and orthanc_hosted_staticfile(uri=_resource, method=_method):
			adata.update({ 'granted': True, 'validity': 5, 
				gapi.API_MESSAGE: 'ohif-static-asset' if 'ohif' in _resource else 'static-asset'
			})

		# Allow requests to Orthanc /system endoint
		elif _resource == '/system' and self.form.is_valid() and getattr(self.form, 'user', None) \
			and self.form.server.user_has_access(self.form.user):
			adata.update({ 'granted': True, 'validity': 1, gapi.API_MESSAGE: 'system-config' })

		# Authorize requests for Sonador users
		elif self.form.is_valid() and getattr(self.form, 'user', None): 

			# Valid authorization forms resolve to the "Sonador" internal user
			# or to a user account. The internal user is a superadmin authorized
			# to access or modify any imaging resource. User accounts require
			# permission to access the resource they have requested. Resource requests
			# can be verified by calling the user_has_perm method of the imaging server model.
			if self.form.user == 'sonador' or getattr(self.form.user, 'pk', None):

				if self.form.user == SONADOR_USERNAME:
					granted = True
					validity = self.form.expires_in

				else:
					granted, validity = self.form.server.user_has_perm(
						self.form.user, self.form.cleaned_data.get('uri'), self.form.cleaned_data.get('orthanc_id'),
						self.form.cleaned_data.get('method'), self.form.cleaned_data.get('level'), 
						dicom_uid=self.form.cleaned_data.get('dicom_uid'))

				if granted:

					if validity is None:
						validity = self.form.expires_in
					
					# The Orthanc advanced authorization plugin expects a response that specifies
					# whether access to the resource should be granted, and for how long.
					adata.update({ 'granted': granted, 'validity': validity, gapi.API_MESSAGE: 'resource-auth' })

		# Deny requests from unknown users
		if not adata.get('granted'):
			adata.update({ 'granted': False })

		if not adata.get('granted'):
			logger.error('Token rejected: user="%s" level="%s" orthanc-id="%s resource="%s" method="%s"\nresponse=%s\nrequest=%s' % (
				_user, _level, _orthanc_id, _resource, _method, adata, {
					**omit(self.form.cleaned_data, ('token_value',)),
					'token_value': masked_value(self.form.cleaned_data.get('token_value')) if self.form.cleaned_data.get('token_value') else '(null)',
				}
			))

		return adata

	def get_data(self, context, cache_response=False):
		'''	Process the authorization request.
		'''
		# Pull cached response
		if getattr(self, '_cache_auth_response', None):
			return self._cache_auth_response

		# Create authorization response
		adata = super().get_data(context)
		adata = self.get_authorization_response(adata)

		# Cache response (if enabled)
		if gsetting('CACHE_ENABLED') and adata:
			self.cache_set_authorization_response(adata)

		return adata

	def post(self, request, *args, **kwargs):
		'''	Process authorization request from Orthanc
		'''
		# Retrieve imaging server from cache
		try: server = self.getImagingServer(*args, **kwargs)
		except self.imagingserver_class.DoesNotExist as err:
			return guru_page_not_found(self.request, err)

		# Retrieve cached response
		if gsetting('CACHE_ENABLED'):
			
			_cache_key, _auth_response = self.cache_get_authorization_response(request, *args, **kwargs)
			if _auth_response:

				logger.debug('Response retrieved from cache. cache-key="%s" response="%s"' % (
					_cache_key, _auth_response, 
				))

				setattr(self, '_cache_auth_response', _auth_response)
				return self.render_to_response(_auth_response)

		return super(OrthancServiceAuthorizationView, self).post(request, *args, **kwargs)
