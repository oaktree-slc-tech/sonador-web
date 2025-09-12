'''	Orthanc Service Token Authorization View: primary view instances used to authorization access
	to Orthanc resources.
'''
import logging, posixpath

from guru import apisettings as gapi
from guru.errors import OperationError, GuruFormError
from guru.forms.helpers import validate_form_data
from guru.helpers.utils.object import omit

from secure.models import ApiAccess, ApiAccessToken
from secure.helpers import server_decrypt_data, masked_value

from orthancapi.helpers import orthanc_hosted_staticfile

from ....apisettings import SONADOR_USERNAME
from ...forms.orthanc import OrthancServiceAuthorizationForm
from .base import SonadorServiceAuthorizationBaseView, OrthancServiceImagingServerMixin

logger = logging.getLogger(__name__)


class OrthancServiceAuthorizationView(OrthancServiceImagingServerMixin, SonadorServiceAuthorizationBaseView):
	'''	API view which can be used to process authorization requests from Orthanc
	'''
	formclass = OrthancServiceAuthorizationForm
	
	def get_form_kwargs(self, *args, **kwargs):
		form_kwargs = super().get_form_kwargs(*args, **kwargs)
		form_kwargs['server'] = self.getImagingServer(*args, **kwargs)
		return form_kwargs

	def get_auth_request_params(self, *args, **kwargs):
		'''	Retrieve authorization request components
		'''
		# Request components
		_user = getattr(self.form, 'user', None)
		_orthanc_id = self.form.data.get('orthanc_id') or ''		
		_level = self.form.data.get('level') or ''
		_method = self.form.data.get('method') or ''
		_resource = self.form.data.get('uri') or ''
		_,_rtype = posixpath.splitext(_resource)

		return _user, _orthanc_id, _level, _method, _resource, _rtype

	def get_authorization_response(self, adata, *args, **kwargs):
		'''	Parse the authorization request and create the authorization response
		'''
		# Auth request components
		_user, _orthanc_id, _level, _method, _resource, _rtype = self.get_auth_request_params()

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

	def get_data(self, context):
		'''	Process the authorization request.
		'''
		adata = super().get_data(context)		

		# Auth request components
		_user, _orthanc_id, _level, _method, _resource, _rtype = self.get_auth_request_params()

		# Create authorization response
		adata = self.get_authorization_response(adata)
		return adata

	def post(self, request, *args, **kwargs):
		'''	Process authorization request from Orthanc
		'''
		# Retrieve imaging server from cache
		try: server = self.getImagingServer(*args, **kwargs)
		except self.imagingserver_class.DoesNotExist as err:
			return guru_page_not_found(self.request, err)

		return super(OrthancServiceAuthorizationView, self).post(request, *args, **kwargs)
