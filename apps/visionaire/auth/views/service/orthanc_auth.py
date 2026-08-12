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
from ....audit import apisettings as audit_api
from ....audit import helpers as audit_helpers
from ....audit.events import best_effort_audit
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

	# Namespace for the companion audit entry written alongside a cached authorization
	# response. See `cache_set_audit_context` for why the audit context cannot simply be
	# added to the cached response itself.
	auth_response_audit_cache_prefix = b'orthanc-acl-audit|'

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
		_action = form_data.get('action') or ''
		_,_rtype = posixpath.splitext(_resource)

		return _user, _orthanc_id, _level, _method, _resource, _rtype, _action

	def cache_auth_response_key(self, *args, form_data=None, **kwargs):
		'''	Retrieve the hashed cache key for the authorization response
		'''
		# Retrieve request components
		form_data = form_data or self.getRequestJsonData(self.request)
		_, orthanc_id, level, method, resource, _, action = self.get_auth_request_params(form_data=form_data, **kwargs)
		# `action` MUST be part of the cache key: it can change the auth decision for the
		# SAME resource (a comment write vs. a plain modify), so omitting it would let a
		# grant for one action be replayed for another (cache poisoning).
		_components = self.auth_response_cache_sep.join(str(_c) for _c in (orthanc_id, level, method, resource, action) if _c)

		# Generate hash key
		return self.auth_response_cache_key_template % (
			(gsetting('SECRET_KEY') or create_token()).encode(self.auth_response_encoding),
			('%s%s%s' % (form_data.get('token_key') or create_token(), self.auth_response_cache_sep, 
				form_data.get('token_value') or create_token())).encode(self.auth_response_encoding),
			self.auth_response_cache_prefix.encode(self.auth_response_encoding),
			_components.encode(self.auth_response_encoding))

	def cache_audit_context_digest(self, cache_key):
		'''	Derive the cache digest of the audit context that accompanies a cached
			authorization response. Namespaced off the same key so the two entries are
			written and read for exactly the same request.
		'''
		return blake3(self.auth_response_audit_cache_prefix + cache_key).hexdigest()

	def audit_request_context(self, adata=None):
		'''	Assemble the audit context for the current authorization request.

			Reads `self.form.user` directly rather than the user returned by
			`get_auth_request_params`: that helper does `getattr(self, 'None', None)`, which
			looks up an attribute literally named "None" and therefore always resolves to
			`None`. Feeding it into the audit path is what left every event in the 2024
			prototype without an actor. Repairing the helper would change the existing token
			rejection log line and is tracked separately.

			@input adata (dict, default=None): the authorization response, when available

			@returns tuple (user, entity_id, context)
		'''
		cleaned = self.form.cleaned_data if hasattr(self.form, 'cleaned_data') else {}
		adata = adata or {}

		# The resource identifier a reviewer would search on. Identifiers only: no patient
		# demographics and no DICOM tag content ever enter the record.
		entity_id = cleaned.get('dicom_uid') or cleaned.get('orthanc_id')

		# Drop the query string before the URI goes anywhere. A DICOMweb search carries
		# patient demographics as ordinary query parameters, and this context is also
		# written to the companion cache entry -- sanitizing here keeps those values out of
		# the cache as well as out of the record.
		_uri, _query_keys = audit_helpers.sanitize_uri(cleaned.get('uri'))

		return getattr(self.form, 'user', None), entity_id, {
			audit_api.AUDIT_DETAIL_ORTHANC_ID: cleaned.get('orthanc_id'),
			audit_api.AUDIT_DETAIL_DICOM_UID: cleaned.get('dicom_uid'),
			audit_api.AUDIT_DETAIL_LEVEL: cleaned.get('level'),
			audit_api.AUDIT_DETAIL_METHOD: cleaned.get('method'),
			audit_api.AUDIT_DETAIL_URI: _uri,
			audit_api.AUDIT_DETAIL_QUERY_KEYS: _query_keys,
			audit_api.AUDIT_DETAIL_ACTION: cleaned.get('action'),
			audit_api.AUDIT_DETAIL_IMAGING_SERVER: audit_helpers.server_audit_label(
				getattr(self.form, 'server', None)),
			audit_api.AUDIT_DETAIL_VALIDITY: adata.get('validity'),

			# The credential *name* is recorded so a reviewer can tell a session from an API
			# token from a static-asset request. The credential *value* never is.
			audit_api.AUDIT_DETAIL_TOKEN_KEY: cleaned.get('token_key'),
		}

	def cache_get_authorization_response(self, request, *args, **kwargs):
		''' Retrieve an authorization response from the system cache
		'''
		_cache_key = self.cache_auth_response_key(*args, **kwargs)
		_cache_key_digest = blake3(_cache_key).hexdigest()
		_cache_response = cache.get(_cache_key_digest)

		logger.debug('Response retrieved from cache: view="%s" cache-key="%s" digest="%s"": "%s"' % (
			self.auth_response_cache_prefix, _cache_key, _cache_key_digest,  _cache_response or ''
		))

		# A cache hit returns before `get_authorization_response` runs and before the form
		# is built, so the emit site on the decision path never sees it. Auditing only there
		# would record every denial but only the FIRST of each repeated grant -- an audit log
		# systematically missing successful PHI accesses while looking complete. Emit here so
		# a cached grant is indistinguishable in completeness from an uncached one.
		if _cache_response:
			self.audit_cached_authorization_response(_cache_key, request=request)

		return _cache_key, json.loads(_cache_response) if _cache_response else None

	@best_effort_audit
	def audit_cached_authorization_response(self, cache_key, request=None):
		'''	Emit an audit event for an authorization response served from cache.

			The context is replayed from the companion cache entry because none of it is
			recoverable at this point in the request: the form has not been built.

			Guarded because it runs inside the cache-read path of a live authorization
			request: a cache backend that is unreachable, or a companion entry that fails to
			decode, must cost an audit record and nothing else.
		'''
		from ....audit.events import emit_audit_event

		_audit_context = cache.get(self.cache_audit_context_digest(cache_key))
		if not _audit_context:

			# The response and its companion are written together with the same timeout, so
			# this means the entries have diverged. The access is still recorded -- an event
			# with thin context beats a missing one -- and the gap is made visible.
			logger.error('Audit context missing for a cached authorization response '
				+ '(digest="%s"). The access is recorded without request context.'
				% self.cache_audit_context_digest(cache_key))
			_audit_context = {}

		else:
			_audit_context = json.loads(_audit_context)

		emit_audit_event(sender=type(self), event_type=audit_api.AUDIT_RESOURCE_ACCESS_CACHED,
			user=_audit_context.get('user'), outcome=True, request=request,
			entity_id=_audit_context.get('entity_id'),
			context={**(_audit_context.get('context') or {}), audit_api.AUDIT_DETAIL_CACHE_HIT: 'true'},
			outcome_desc=_audit_context.get('outcome_desc'))

	@best_effort_audit
	def cache_set_audit_context(self, cache_key, timeout, adata):
		'''	Write the audit context that accompanies a cached authorization response.

			This is a SEPARATE cache entry rather than extra keys on the cached response,
			because `post()` renders the cached response straight back to Orthanc -- anything
			added to it is echoed over the wire in the authorization reply, not merely held
			internally.

			The timeout is the one the response entry was written with, passed in by the
			caller so the two entries always expire together. Deriving it independently here
			would let the companion outlive or predecease the response it belongs to.
		'''
		_user, _entity_id, _context = self.audit_request_context(adata=adata)
		_username, _user_pk = (getattr(_user, 'username', None) or _user, getattr(_user, 'pk', None)) \
			if _user is not None else (None, None)

		cache.set(self.cache_audit_context_digest(cache_key), json.dumps({
			'user': {'username': _username, 'pk': _user_pk} if _username else None,
			'entity_id': _entity_id,
			'context': _context,
			'outcome_desc': adata.get(gapi.API_MESSAGE),
		}, default=str), timeout)

	def cache_set_authorization_response(self, authorization_response, *args, **kwargs):
		'''	Cache an authorization response from the system cache
		'''
		if authorization_response.get('granted'):

			_cache_key = self.cache_auth_response_key(*args, form_data=self.form.cleaned_data, **kwargs)
			_cache_key_digest = blake3(_cache_key).hexdigest()

			# NOTE: `granted` is a bool, so this resolves to a 1-second timeout rather than
			# the grant's validity -- a pre-existing defect, preserved here deliberately
			# because changing the cache lifetime is out of scope for the audit work. It is
			# hoisted into a local so the companion audit entry below is guaranteed to expire
			# with the response it describes, whatever this expression is later corrected to.
			_cache_timeout = authorization_response.get('granted') or self.form.expires_in

			cache.set(_cache_key_digest, json.dumps(authorization_response), _cache_timeout)

			# No-op when auditing is disabled, and guarded when it is not, so writing the
			# companion entry can never interfere with caching the response itself.
			self.cache_set_audit_context(_cache_key, _cache_timeout, authorization_response)

			_test = cache.get(_cache_key_digest)

			logger.debug('Auth response cached. view="%s" cache-key="%s" digest="%s" response="%s" valid="%s"' % (
				self.auth_response_cache_prefix, _cache_key, _cache_key_digest, authorization_response,
				authorization_response.get('validity') or self.form.expires_in,
			))

	def get_authorization_response(self, adata, *args, **kwargs):
		'''	Parse the authorization request and create the authorization response
		'''
		# Auth request components
		_user, _orthanc_id, _level, _method, _resource, _rtype, _action = self.get_auth_request_params(
			form_data=self.form.cleaned_data if self.form.is_valid() else self.form.data)

		# Allow requests for static assets
		if self.form.cleaned_data.get('token_key') == 'static-asset' and self.form.user:
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
						dicom_uid=self.form.cleaned_data.get('dicom_uid'),
						action=self.form.cleaned_data.get('action'))

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
				_user or getattr(self.form, 'user', None) or '(null)', _level, _orthanc_id, _resource, _method, adata, {
					**omit(self.form.cleaned_data, ('token_value',)),
					'token_value': masked_value(self.form.cleaned_data.get('token_value')) if self.form.cleaned_data.get('token_value') else '(null)',
				}
			))

		# Record the decision. Every terminal outcome above -- static asset, /system, a
		# per-resource evaluation, and the closing deny -- passes through here, so grants and
		# denials are audited alike from a single site.
		self.audit_authorization_response(adata)

		return adata

	@best_effort_audit
	def audit_authorization_response(self, adata):
		'''	Emit an audit event for an access-control decision.

			Best-effort end to end: assembling the context is guarded as well as the emit, so
			neither a slow broker nor an unexpected form state can change the decision this
			view just made or the response Orthanc receives.
		'''
		from ....audit.events import emit_audit_event

		_user, _entity_id, _context = self.audit_request_context(adata=adata)

		emit_audit_event(sender=type(self), event_type=audit_api.AUDIT_RESOURCE_ACCESS,
			user=_user, outcome=bool(adata.get('granted')), request=self.request,
			server=getattr(self.form, 'server', None), entity_id=_entity_id, context=_context,
			outcome_desc=adata.get(gapi.API_MESSAGE))

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
