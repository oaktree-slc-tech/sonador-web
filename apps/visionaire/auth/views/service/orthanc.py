import logging, json

from django.views import View

from orthancapi import auth as orthanc_authapi

import guru.apisettings as gapi
from guru.helpers import operation_results
from guru.helpers.compatability import guru_page_not_found, guru_permission_denied
from guru.helpers.user import user_displayname

from microservices.control import server_controlurl

from ....views.base import SonadorApiRestView

from ...helpers import create_session_token
from ...forms.orthanc import OrthancServiceAuthorizationForm

from .base import SonadorServiceAuthorizationBaseView, OrthancServiceImagingServerMixin

logger = logging.getLogger(__name__)


class OrthancAuthUserProfileView(OrthancServiceImagingServerMixin, SonadorServiceAuthorizationBaseView):
	'''	API view which can be used to process token authorization requests from Sonador
	'''
	formclass = OrthancServiceAuthorizationForm

	def get_form_kwargs(self, *args, **kwargs):
		form_kwargs = super().get_form_kwargs(*args, **kwargs)
		form_kwargs['server'] = self.getImagingServer(*args, **kwargs)
		return form_kwargs

	def get_data(self, context):
		'''	Process the token decode event
		'''
		adata = super().get_data(context)

		# Retrive user profile
		if self.form.is_valid() and getattr(self.form, 'user', None):

			# Labels and permissions the user is authorized for
			authorized_labels = []
			permissions = []
			if self.form.user.is_superuser:
				authorized_labels.append('*')
				permissions.append('all')

			adata.update({
				'server': self.form.server.pk, 'pk': self.form.user.pk, 'username': self.form.user.username, 
				'name': user_displayname(self.form.user), 'email': self.form.user.email,
				'authorized-labels': authorized_labels, 'permissions': permissions,
				'validity': 60,
			})
		
		logger.warning('User profile response:\n%s' % adata)

		return adata

	def post(self, request, *args, **kwargs):
		# Retrieve imaging server from cache
		try: server = self.getImagingServer(*args, **kwargs)
		except self.imagingserver_class.DoesNotExist as err:
			return guru_page_not_found(self.request, err)

		return super().post(request, *args, **kwargs)


class OrthancAuthTokenGenerateView(OrthancServiceImagingServerMixin, View):
	'''	API view used to generate Orthanc Tokens: 
	'''
	def put(self, request, serverid, token_type, *args, **kwargs):
		'''	Process token generation request
		'''
		kwargs[self.imagingserver_request_param] = serverid

		# Retrieve imaging server from cache
		try: server = self.getImagingServer(*args, **kwargs)
		except self.imagingserver_class.DoesNotExist as err:
			return guru_page_not_found(self.request, err)

		logger.warning('Token authorization request: user=%s\n%s' % (self.request.user, self.request.body))

		return operation_results({
			'request': json.loads(request.body),
			'token': 'hello-world',
			# 'url': '/ohif/viewer',
		})


class OrthancAuthTokenDecodeView(OrthancServiceImagingServerMixin, SonadorServiceAuthorizationBaseView):
	'''	API view used to decode Orthanc Explorer 2 Tokens
	'''
	formclass = OrthancServiceAuthorizationForm

	def get_form_kwargs(self, *args, **kwargs):
		form_kwargs = super().get_form_kwargs(*args, **kwargs)
		form_kwargs['server'] = self.getImagingServer(*args, **kwargs)
		return form_kwargs

	def get_data(self, context):
		'''	Process the token decode event
		'''
		adata = super().get_data(context)

		logger.warning('Token decode request:\n%s' % self.form.data)

		# Decode user requests
		if self.form.is_valid() and getattr(self.form, 'user', None):

			# Ensure that the token includes required components to generate redirect			
			if not self.form.token_payload or not self.form.token_payload.get('orthanc-resource'):
				adata[gapi.API_ERROR] = 'Invalid Orthanc authorization token, does not specify a resource'
			elif not self.form.session:
				adata[gapi.API_ERROR] = 'Invalid Orthanc session decode request, token does not include a valid user session. ' \
					+ 'Unable to create redirect token.'

			# Create redirect URL
			if self.form.token_payload.get('orthanc-resource') == 'oe2':
				adata.update({
					'token-type': orthanc_authapi.TokenType.ORTHANC_EXPLORER2,
					'redirect-url': server_controlurl(
						self.form.server, 'ui/app/index.html?token=%s' % create_session_token(self.form.session.session_key))
				})

		logger.warning('Token decode response:\n%s' % adata)
		return adata

	def post(self, request, *args, **kwargs):
		'''	Process auth token decode request
		'''
		# Retrieve imaging server from cache
		try: server = self.getImagingServer(*args, **kwargs)
		except self.imagingserver_class.DoesNotExist as err:
			return guru_page_not_found(self.request, err)

		return super().post(request, *args, **kwargs)