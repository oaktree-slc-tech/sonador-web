import logging, six, copy
from six.moves.urllib import parse as urlparse

from django import forms
from django.core import signing
from django.shortcuts import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import RedirectView

from django.contrib import auth
from django.contrib.sessions.backends.db import SessionStore

from guru.errors import OperationError
from guru.helpers.compatability import guru_page_not_found
from guru.helpers.urls import merge_url_querystring

from secure.models import ApiAccessToken

from wgtauth.apisettings import OAUTH_ACCESS_TOKEN, OAUTH_TOKEN_TYPE, OAUTH_TOKEN_TYPE_BEARER, OAUTH_EXPIRATION

from ...views import JSONFormApiView
from ...helpers import SESSION_SALT, ACCESS_TOKEN_MAX_AGE, API_ACCESS_TOKEN_QSPARAM, API_ACCESS_APITOKEN_QSPARAM, \
	API_REFERRER_REFERER_HEADER
from ...models import PacsImagingServer

from .. import hexsigning

logger = logging.getLogger(__name__)


DEFAULT_AUTH_EXPIRES_IN = 30


class ServiceAuthorizationRequest(object):
	'''	Stub object used to mock requests so that user instances can be retrieved from session
		by a service looking to authenticate a user for a service.
	'''
	def __init__(self, session):
		self.session = session


class OrthancServiceAuthorizationForm(forms.Form):
	'''	Form class which can be used to approve or deny authorization requests from Orthanc.
	'''
	level = forms.CharField(required=True)
	method = forms.CharField(required=True)
	token_key = forms.CharField(required=True)
	token_value = forms.CharField(required=True)

	dicom_uid = forms.CharField(required=False)
	orthanc_id = forms.CharField(required=False)
	uri = forms.CharField(required=False)

	formdata_transforms = {
		'token-key': 'token_key',
		'token-value': 'token_value',
		'orthanc-id': 'orthanc_id',
		'dicom-uid': 'dicom_uid',
	}

	def clean(self, *args, **kwargs):
		'''	Clean data and convert parameters to the format required needed for sessionm
			or API token authorization.
		'''
		cleaned_data = super(OrthancServiceAuthorizationForm, self).clean(*args, **kwargs)

		# Parse authentication from "Referrer" headers
		if cleaned_data.get('token_key') == API_REFERRER_REFERER_HEADER:

			# Retrieve querystring components
			logger.debug('Parse authentication values from referrer:\n%s' % cleaned_data.get('token_value'))
			rparts = urlparse.parse_qs(urlparse.urlparse(cleaned_data.get('token_value')).query) \
					if getattr(urlparse.urlparse(cleaned_data.get('token_value')), 'query', None) \
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
		elif cleaned_data.get('token_key') == API_ACCESS_TOKEN_QSPARAM and ':' in cleaned_data.get('token_value'):
			cleaned_data['token_value'] = '%s %s' % (OAUTH_TOKEN_TYPE_BEARER, cleaned_data.get('token_value'))

		# Parse authentication data
		cleaned_data = self.clean_authdata(cleaned_data)
		return cleaned_data

	def clean_authdata(self, cleaned_data):
		'''	Inspect authentication headers, convert to correct sessions or API tokens, 
			retrieve users and permissions.
		'''
		# Determine the correct token key/value keywords: referrer values take precedence if present
		if cleaned_data.get('referrer_token_key') and cleaned_data.get('referrer_token_value'):
			tokenvalue_kw = 'referrer_token_value'
		else: tokenvalue_kw = 'token_value'

		# Bearer Token (oAuth: JWT/Hex Encoded)
		if (cleaned_data.get(tokenvalue_kw) and OAUTH_TOKEN_TYPE_BEARER in cleaned_data.get(tokenvalue_kw)) \
			or (cleaned_data.get(tokenvalue_kw) == API_ACCESS_TOKEN_QSPARAM and OAUTH_TOKEN_TYPE_BEARER in cleaned_data.get(tokenvalue_kw)):
			
			# Parse base64 encoded token created using django.signing
			cleaned_data = self.decode_session_authdata(cleaned_data, tokenvalue_kw=tokenvalue_kw)
			
		# API token or referrer API token
		elif cleaned_data.get('token_key') in (API_ACCESS_TOKEN_QSPARAM, API_ACCESS_APITOKEN_QSPARAM) \
			or cleaned_data.get('referrer_token_key') in (API_ACCESS_TOKEN_QSPARAM, API_ACCESS_APITOKEN_QSPARAM):

			if cleaned_data.get('referrer_token_key'):
				tvalue = cleaned_data.get('referrer_token_value')
			else: tvalue = cleaned_data.get('token_value')
			
			# Retrieve API token and assign user
			try:
				t = ApiAccessToken.objects.select_related('user').get(pk__iexact=tvalue)
				self.user = t.user
				self.expires_in = DEFAULT_AUTH_EXPIRES_IN
				logger.debug('Token user: %s' % self.user.username)

			except ApiAccessToken.DoesNotExist as err:
				logger.error('Unable to retrieve API token matching request: %s' % cleaned_data.get('token_value'))

		return cleaned_data

	def decode_session_authdata(self, cleaned_data, tokenvalue_kw='token_value'):
		'''	Decode authentication data based on a Sonador session:

			1. base64 encoded JSON web tokens
			2. hex encoded session tokens
		'''
		svalue = copy.deepcopy(cleaned_data.get(tokenvalue_kw))
		logger.debug('Signed Session Token: %s' % svalue)

		try:

			# Convert the signed token to session key
			ssig = svalue.replace(OAUTH_TOKEN_TYPE_BEARER, '').strip()
			logger.debug('Bearer token: %s' % ssig)

			# Determine encoding of the token
			if ssig[:2] == 'h:':
				skey = self.decode_hex_authdata(ssig[2:])
			else:
				skey = self.decode_base64_authdata(ssig)
			
			cleaned_data['session'] = skey

			# Retrieve session from backend storage
			logger.debug('Bearer token session: %s' % skey)
			self.session = SessionStore(session_key=skey)
			self.user = auth.get_user(ServiceAuthorizationRequest(self.session))
			self.expires_in = DEFAULT_AUTH_EXPIRES_IN
			logger.debug('Token user: %s' % self.user.username)

		except signing.BadSignature as err:
			logger.error('Unable to retrieve session ID from the token, mismatched signature.\n%s'
				% cleaned_data.get(tokenvalue_kw))

		return cleaned_data
		

	def decode_base64_authdata(self, ssig):
		'''	Decode a Base64 session token
		'''
		return signing.loads(ssig, salt=SESSION_SALT)

	def decode_hex_authdata(self, ssig):
		'''	Decode a hexadecimal encoded session token
		'''
		return hexsigning.loads(ssig, salt=SESSION_SALT)


class OrthancServiceAuthorizationView(JSONFormApiView):
	'''	API view 
	'''
	formclass = OrthancServiceAuthorizationForm

	def getRequestJsonData(self, *args, **kwargs):
		data = super(OrthancServiceAuthorizationView, self).getRequestJsonData(*args, **kwargs)

		# Apply formdata transforms to transform request keys to the correct form field keys
		fclass = self.get_form_class()
		if hasattr(fclass, 'formdata_transforms') and isinstance(fclass.formdata_transforms, dict):
			for k, v in six.iteritems(fclass.formdata_transforms):
				
				if k in data:
					fdata = data.pop(k)
					data[v] = fdata

		logger.debug('Orthanc authorization requestion data:\n%r' % data)
		return data

	def get_data(self, context):
		adata = super(OrthancServiceAuthorizationView, self).get_data(context)

		# Authorize requests for Sonador users
		if self.form.is_valid() and getattr(self.form, 'user', None) and self.form.user.pk:
			adata.update({
				'granted': True,
				'validity': self.form.expires_in,
			})

		# Deny requests from unknown users
		else: adata.update({ 'granted': False })

		return adata

	def form_valid(self, form):
		return super(OrthancServiceAuthorizationView, self).form_valid(form)


class OrthancSecureUriRedirectView(RedirectView):
	'''	View which can be used to redirect 
	'''
	model = PacsImagingServer
	model_objectid_fieldname = 'serverid'
	server_url_attr = None

	def __init__(self, *args, **kwargs):
		super(OrthancSecureUriRedirectView, self).__init__(*args, **kwargs)

	def get(self, *args, **kwargs):
		if not getattr(self, 'server_url_attr', None):
			raise OperationError('Invalid view configuration, so server URL attribute specified')

		try: self.server = self.model.objects.get(pk=kwargs.get(self.model_objectid_fieldname))
		except self.model.DoesNotExist as err:
			return guru_page_not_found(self.request, err)

		return super(OrthancSecureUriRedirectView, self).get(*args, **kwargs)

	def get_redirect_url(self, *args, **kwargs):
		'''	Redirect to the Orthanc URL specified by the server URL attribute. Includes
			a signed token value in the URL based on the current user session.
		'''
		return merge_url_querystring(getattr(self.server, self.server_url_attr), {
				'token': 'h:%s' % hexsigning.dumps(self.request.session.session_key, salt=SESSION_SALT),
			})

