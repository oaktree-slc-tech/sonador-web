import logging, json, datetime

from django.views import View
from django.utils import timezone

from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session

from orthancapi import auth as orthanc_authapi

import guru.apisettings as gapi
from guru.helpers import operation_results, create_token
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
		if self.form.is_valid() and getattr(self.form, 'user', None) and self.form.server.user_has_access(self.form.user):

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
		
		logger.debug('Orthac user profile response:\n%s' % adata)

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

		# Convert request to JSON
		try: rdata = orthanc_authapi.TokenCreationRequest(**json.loads(self.request.body))
		except ValueError as err:
			return operation_results({
					gapi.API_ERROR: 'invalid-request',
					gapi.API_MESSAGE: 'Unable to load request JSON due to an error: %s' % err,
				}, status_code=400)

		if orthanc_authapi.TokenType.VIEWER_INSTANT_LINK:

			# Ensure that the request includes an expiry
			skey = 'resource-grant:%s:%s' % (server.pk, create_token())
			sexp = rdata.expiration_date or timezone.now()+datetime.timedelta(seconds=rdata.validity_duration)

			# Create a resource grant and store it as a Django session. The session is explicitly created first
			# to provide a structured key name that includes the type of session (resource-grant) and the 
			# the ID of the server. The session store instance is the retrieved separately once the database
			# column has been populated.
			Session(pk=skey, expire_date=sexp).save()
			
			# Initialize session store
			s = SessionStore(session_key=skey)
			s['type'] = token_type

			# Specify the account which authorized the grant and the resources. The account that authorized
			# access to the resources is included in the grant, but not shared in the token. When the token
			# is validated, the validation endpoint will ensure that the authorizing user has access to all resources
			# before allowing the grant.
			s['authorizer'] = self.request.user.pk
			s['resources'] = ['%s:%s' % (r.level.value, r.orthanc_id) for r in rdata.resources]
			s.save()

			# Generate token request from session ID and resource list
			_token = create_session_token(
				s.session_key, token_payload={ 'resources': [r.orthanc_id for r in rdata.resources] })

			return operation_results({ 'request': rdata.dict(), 'token': _token })

		raise NotImplementedError('Invalid token type: %s' % token_type)


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

		return adata

	def post(self, request, *args, **kwargs):
		'''	Process auth token decode request
		'''
		# Retrieve imaging server from cache
		try: server = self.getImagingServer(*args, **kwargs)
		except self.imagingserver_class.DoesNotExist as err:
			return guru_page_not_found(self.request, err)

		return super().post(request, *args, **kwargs)