'''	View instances which provide API endpoints conformant with the Orthanc Advanced Authorization
	Plugin: https://orthanc.uclouvain.be/book/plugins/authorization.html
'''
import logging, json, datetime

from django.contrib.sessions.backends.db import SessionStore
from django.views import View
from django.utils import timezone
from django.contrib.sessions.models import Session
from django.contrib.auth import get_user_model

from orthancapi import auth as orthanc_authapi

import guru.apisettings as gapi
from guru.helpers import operation_results, create_token
from guru.helpers.compatability import guru_page_not_found, guru_permission_denied
from guru.helpers.user import user_displayname
from guru.helpers.utils.object import pick, omit

from microservices.control import server_controlurl

from ....apisettings import SONADOR_USERNAME, SONADOR_USER_PK, SONADOR_USER_LABEL
from ....views.base import SonadorApiRestView

from ...helpers import create_session_token
from ...forms.orthanc import ImagingServerIntegrationAuthorizationForm, OrthancServiceAuthorizationForm

from .base import SonadorServiceAuthorizationBaseView, OrthancServiceImagingServerMixin
from .integrations import UserProfileAuthorizationView

logger = logging.getLogger(__name__)


class PacsImagingServerAuthUserProfileView(OrthancServiceImagingServerMixin, UserProfileAuthorizationView):
	'''	API view which can be used to retrieve the user profiles based on token authorization requests.
		Generally follows the "Token Introspection" endpoint specified by the oAuth2 standard:
		https://www.oauth.com/oauth2-servers/token-introspection-endpoint/

		and is used by services which integrate with Sonador to retrieve information about users
		requesting access to resources managed by the service. Provides support for both Sonador generated
		and remote IdP service tokens.
	'''
	formclass = ImagingServerIntegrationAuthorizationForm
	validity_duration = 60

	def get_form_kwargs(self, *args, **kwargs):
		form_kwargs = super().get_form_kwargs(*args, **kwargs)
		form_kwargs['server'] = self.getImagingServer(*args, **kwargs)
		return form_kwargs

	def user_has_perm(self, *args, **kwargs):
		return self.form.server.user_has_access(self.form.user)

	def createProfileResponse(self, *args, **kwargs):
		'''	Add authorization and validity parameters to the response
		'''
		return { 'validity': getattr(self.form, 'expires_in', None) or self.validity_duration }

	def getUserProfileJson(self, user, response):
		'''	Retrieve JSON for the provided user instance including the groups to which the user
			has access which are associated with the server.
		'''
		response = super().getUserProfileJson(user, response)
		response['user']['groups'] = [self.getGroupJson(g) 
			for g in self.form.user.groups.filter(server_authorizations__server=self.form.server)]
		response['server'] = self.getImagingServer().pk
		response['user']['permissions'] = [
			k for k,v in self.getImagingServer().server_perms(user).items() if (v and k not in ('is_superuser', 'is_staff'))]

		return response

	def post(self, request, *args, **kwargs):
		# Retrieve imaging server from cache
		try: server = self.getImagingServer(*args, **kwargs)
		except self.imagingserver_class.DoesNotExist as err:
			return guru_page_not_found(self.request, err)

		return super().post(request, *args, **kwargs)


class OrthancAuthUserProfileView(PacsImagingServerAuthUserProfileView):
	'''	API view which can be used to process token authorization requests from Sonador and return a 
		user profile in the response. Conforms to the Orthanc User Profile view API specification:
		https://orthanc.uclouvain.be/book/plugins/authorization.html#get-user-profile-user-get-profile.		
	'''
	formclass = OrthancServiceAuthorizationForm
	
	def getUserProfileJson(self, user, response):
		'''	Retrieve Orthanc user profile JSON data required by the Orthanc Advanced Authorization plugin
		'''
		# User UID
		user_uid = self.form.user.pk if isinstance(self.form.user, get_user_model()) \
			else SONADOR_USER_PK if isinstance(self.form.user, str) \
			else None

		if not user_uid:
			raise ValueError('Unable to create user profile, invalid user UID=%s' % user_uid)

		# Username
		username = self.form.user.username if isinstance(self.form.user, get_user_model()) \
			else self.form.user if isinstance(self.form.user, str) \
			else None
		if not username:
			raise ValueError('Unable to create user profile, invalid username="%s"' % username)

		# User display name
		user_label = user_displayname(self.form.user) if isinstance(self.form.user, get_user_model()) \
			else SONADOR_USER_LABEL if isinstance(self.form.user, str) \
			else None

		if not user_label:
			raise ValueError('Unable to create user profile, invalid uesr label="%s"' % user_label)

		# User email
		user_email = self.form.user.email if isinstance(self.form.user, get_user_model()) else None		

		# Labels and permissions the user is authorized for
		authorized_labels = ['all']
		permissions = []
		if (isinstance(self.form.user, get_user_model()) and self.form.user.is_superuser) \
			or (isinstance(self.form.user, str) and self.form.user == SONADOR_USERNAME):
			authorized_labels.append('*')
			permissions.append('all')

		response.update({
			'name': user_label, 'authorized-labels': authorized_labels, 'permissions': permissions,
		})

		return response


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
		if self.form.is_valid() and getattr(self.form, 'user', None) and self.form.server.user_has_access(self.form.user):

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