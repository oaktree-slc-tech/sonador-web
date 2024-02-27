import logging, six, copy, base64, posixpath
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

from secure.models import ApiAccess, ApiAccessToken
from secure.helpers import server_decrypt_data

from wgtauth.apisettings import BASIC_AUTH_TYPE, \
	OAUTH_ACCESS_TOKEN, OAUTH_TOKEN_TYPE, OAUTH_TOKEN_TYPE_BEARER, OAUTH_EXPIRATION

from ....views import JSONFormApiView
from ....helpers import SESSION_SALT, ACCESS_TOKEN_MAX_AGE, \
	API_ACCESS_SERVER_TOKEN, API_ACCESS_TOKEN_QSPARAM, API_ACCESS_APITOKEN_QSPARAM, \
	API_REFERRER_REFERER_HEADER
from ....models import PacsImagingServer

from ... import hexsigning
from ...helpers import create_session_token
from ...forms.base import ServiceAuthorizationRequest
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

	def get_data(self, context):
		'''	Process the authorization request.
		'''
		adata = super().get_data(context)

		# Allow requests for static assets
		_resource = self.form.data.get('uri') or ''
		_,_rtype = posixpath.splitext(_resource)
		if self.form and _rtype.replace('.', '').lower() in ('css', 'js', 'ico', 'woff2', 'ttf'):
			adata.update({ 'granted': True, 'validity': 1 })

		# Allow requests to Orthanc OHIF plugin
		elif _resource == '/ohif/viewer/' or '/ohif/assets/' in _resource:
			adata.update({ 'granted': True, 'validity': 5 })

		# Authorize requests for Sonador users
		elif self.form.is_valid() and getattr(self.form, 'user', None): 

			# Valid authorization forms resolve to the "Sonador" internal user
			# or to a user account. The internal user is a superadmin authorized
			# to access or modify any imaging resource. User accounts require
			# permission to access the resource they have requested. Resource requests
			# can be verified by calling the user_has_perm method of the imaging server model.			
			if self.form.user == 'sonador' \
				or (self.form.user.pk and self.form.server.user_has_perm(
						self.form.user, self.form.cleaned_data.get('uri'), self.form.cleaned_data.get('orthanc_id'),
						self.form.cleaned_data.get('method'), self.form.cleaned_data.get('level'))):
				
				# The Orthanc advanced authorization plugin expects a response that specifies
				# whether access to the resource should be granted, and for how long.
				adata.update({ 'granted': True, 'validity': self.form.expires_in, })				

		# Deny requests from unknown users
		if not adata.get('granted'):
			adata.update({ 'granted': False })

		if not adata.get('granted'):
			logger.warning('Token validation request rejected: resource=%s\n%s' % (self.form.cleaned_data.get('uri'), adata))
		return adata

	def post(self, request, *args, **kwargs):
		'''	Process authorization request from Orthanc
		'''
		# Retrieve imaging server from cache
		try: server = self.getImagingServer(*args, **kwargs)
		except self.imagingserver_class.DoesNotExist as err:
			return guru_page_not_found(self.request, err)

		return super(OrthancServiceAuthorizationView, self).post(request, *args, **kwargs)


class OrthancSecureUriRedirectView(RedirectView):
	'''	View which can be used to redirect
	'''
	model = PacsImagingServer
	model_objectid_fieldname = 'serverid'
	server_url_attr = None
	token_payload = None
	querystring_attrs = None

	def __init__(self, *args, **kwargs):
		super(OrthancSecureUriRedirectView, self).__init__(*args, **kwargs)

		# Ensure that an imaging server URL attribute is specified for redirect
		if not getattr(self, 'server_url_attr', None):
			raise OperationError('Invalid view configuration, so server URL attribute specified')

		# Ensure that token payload and querystring parameters are provided as dictionaries
		if self.token_payload and not isinstance(self.token_payload, dict):
			raise TypeError('Invalid Orthanc payload for the view, must be a JSON object/dict')
		if self.querystring_attrs and not isinstance(self.querystring_attrs, dict):
			raise TypeError('Invalid querystring parameters for view instance, must be a set of key/value pairs (dict)')

	def get(self, *args, **kwargs):

		try: self.server = self.model.objects.get(pk=kwargs.get(self.model_objectid_fieldname))
		except self.model.DoesNotExist as err:
			return guru_page_not_found(self.request, err)

		return super(OrthancSecureUriRedirectView, self).get(*args, **kwargs)

	def get_redirect_url(self, *args, **kwargs):
		'''	Redirect to the Orthanc URL specified by the server URL attribute. Includes
			a signed token value in the URL based on the current user session.
		'''
		# Add parameters to redirect, including token
		_query = copy.deepcopy(self.querystring_attrs) if self.querystring_attrs else {}
		_query['token'] = create_session_token(
			self.request.session.session_key, token_payload=copy.deepcopy(self.token_payload) if self.token_payload else None)

		# Create redirect URL
		return merge_url_querystring(getattr(self.server, self.server_url_attr), _query)


class SecureApiLoginView(View):
	'''	Create a session and return a bearer token for an oAuth API session. IMPORTANT:
		the view will authenticate users and provide access to the API as part of an oAuth token
		grant workflow. No permissions checking is performed in the view instance and should
		be applied as a decorator in ANY urls file in which the file is used.
	'''
	def get(self, request, *args, **kwargs):
		if not getattr(request, 'user', None):
			return guru_permission_denied(request)

		# Create a login session for the user
		auth.login(request, request.user)
		return operation_results({
			'id_token': request.session.session_key,
			OAUTH_ACCESS_TOKEN: signing.dumps(request.session.session_key, salt=SESSION_SALT),
			OAUTH_TOKEN_TYPE: OAUTH_TOKEN_TYPE_BEARER,
			OAUTH_EXPIRATION: request.session.get_expiry_age(),
		})
