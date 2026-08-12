'''	FHIR `AuditEvent` construction.

	`build_audit_event` is a pure function over plain inputs -- it touches no database, no
	request state, and no transport -- which is what makes the record shape directly
	testable without a broker or a live authorization request.

	IMPORTANT: the model is imported from the R4B subpackage. `fhir.resources` 8.x resolves
	the bare `fhir.resources.auditevent` path to R5, where `type`/`subtype` are renamed to
	`category`/`code` and `outcome` becomes a BackboneElement. Writing R4-shaped field
	names against that import is what made the 2024 prototype in !70 structurally invalid.
	R4B is chosen because it is structurally identical to the R4 model named in the original
	requirement and matches the R4-era pin already shipping in the Orthanc plugin.
'''
import logging

from django.utils import timezone

from fhir.resources.R4B.auditevent import AuditEvent

from guru.helpers import gsetting

from ..apisettings import SONADOR_USERNAME, SONADOR_USER_PK, SONADOR_USER_LABEL

from . import apisettings as audit_api
from .apisettings import AUDIT_ACTION_READ, AUDIT_ACTOR_UNKNOWN
from .helpers import sanitize_uri, server_audit_label

logger = logging.getLogger(__name__)


def client_address(request):
	'''	Resolve the client IP for `AuditEvent.agent.network.address`.

		Sonador runs behind nginx, so `REMOTE_ADDR` is the proxy rather than the caller;
		the left-most `X-Forwarded-For` entry is the originating client. That header is
		caller-supplied and therefore only as trustworthy as the proxy in front of it --
		it is recorded as reported, and a reviewer should read it as such.

		@input request (HttpRequest or None)

		@returns str or None
	'''
	if not request:
		return None

	meta = getattr(request, 'META', None) or {}

	forwarded = meta.get('HTTP_X_FORWARDED_FOR')
	if forwarded:
		return forwarded.split(',')[0].strip() or None

	return meta.get('REMOTE_ADDR') or None


def resolve_actor(user):
	'''	Resolve the acting identity to the (username, altId) pair recorded on `agent[0]`.

		The authorization form resolves to one of three things, and all three have to
		produce a usable actor:

		*	a Django `User`;
		*	the literal string `'sonador'`, the internal superuser, which has no database
			row and whose identity comes from `visionaire.apisettings`;
		*	`None`, for a request carrying no resolvable credential. A denial of an
			unauthenticated request is precisely the record a reviewer wants, so it is
			written with a placeholder actor rather than dropped.

		A `{'username': ..., 'pk': ...}` mapping is also accepted, for callers that resolved
		the actor earlier and no longer hold the model instance. The authorization response
		cache is the one such caller: on a cache hit the view returns before the form is
		built, so the actor is replayed from the companion cache entry rather than re-derived.

		@input user (User | str | dict | None)

		@returns tuple (username, alt_id)
	'''
	if user is None:
		return AUDIT_ACTOR_UNKNOWN, None

	# Actor resolved by an earlier request and replayed from the cache.
	if isinstance(user, dict):
		pk = user.get('pk')
		return user.get('username') or AUDIT_ACTOR_UNKNOWN, (str(pk) if pk is not None else None)

	# The internal superuser, which arrives as a bare string rather than a model instance.
	if isinstance(user, str):
		return (SONADOR_USERNAME, str(SONADOR_USER_PK)) if user == SONADOR_USERNAME else (user, None)

	username = getattr(user, 'username', None) or AUDIT_ACTOR_UNKNOWN
	pk = getattr(user, 'pk', None)

	return username, (str(pk) if pk is not None else None)


def resource_access_type_code(method=None, uri=None, orthanc_id=None, dicom_uid=None):
	'''	Derive the DCM type code for a resource-access event.

		The branches mirror the URI classification `OrthancServiceAuthorizationForm.
		clean_auth_request` has already performed: this reads the cleaned `level`,
		`dicom_uid` and `orthanc_id` it produced and the same shared `orthancapi`
		constants, rather than re-parsing the URI a second time and risking a divergent
		answer.

		@returns tuple (code, display)
	'''
	_method = (method or '').lower()
	_uri = uri or ''

	# Destructive first: a delete is a delete regardless of what else the URI looks like.
	if _method == audit_api.AUDIT_METHOD_DELETE:
		return audit_api.DCM_DICOM_STUDY_DELETED

	# Archive/download routes pull imaging data out of the system.
	if audit_api.AUDIT_URI_ARCHIVE in _uri:
		return audit_api.DCM_EXPORT

	# STOW-RS and the native instances endpoint bring imaging data in.
	if _method == audit_api.AUDIT_METHOD_POST and audit_api.AUDIT_URI_INSTANCES in _uri:
		return audit_api.DCM_IMPORT

	# A read that resolved to no specific resource is a search across the archive
	# (QIDO-RS or the native find tooling) rather than an access to one study.
	if _method == audit_api.AUDIT_METHOD_GET and not (orthanc_id or dicom_uid):
		return audit_api.DCM_QUERY

	if audit_api.AUDIT_URI_TOOLS_FIND in _uri or audit_api.AUDIT_URI_TOOLS_FIND_SECURE in _uri:
		return audit_api.DCM_QUERY

	return audit_api.DCM_DICOM_INSTANCES_ACCESSED


def audit_event_codes(event_type, context=None):
	'''	Resolve the (type, subtype) codings for an event.

		@returns tuple (type_coding, subtype_coding); subtype may be None
	'''
	context = context or {}

	if event_type in (audit_api.AUDIT_RESOURCE_ACCESS, audit_api.AUDIT_RESOURCE_ACCESS_CACHED):
		return resource_access_type_code(
			method=context.get(audit_api.AUDIT_DETAIL_METHOD),
			uri=context.get(audit_api.AUDIT_DETAIL_URI),
			orthanc_id=context.get(audit_api.AUDIT_DETAIL_ORTHANC_ID),
			dicom_uid=context.get(audit_api.AUDIT_DETAIL_DICOM_UID)), None

	# An unmapped event type still produces a record: a security alert with no subtype is
	# far better than a dropped event, and it is visibly odd enough to be noticed.
	return audit_api.AUDIT_EVENT_CODES.get(event_type, (audit_api.DCM_SECURITY_ALERT, None))


def audit_event_action(event_type, context=None):
	'''	Resolve `AuditEvent.action` -- the kind of change the event records.
	'''
	context = context or {}

	# Resource access takes its action from the HTTP verb that was authorized.
	if event_type in (audit_api.AUDIT_RESOURCE_ACCESS, audit_api.AUDIT_RESOURCE_ACCESS_CACHED):
		return audit_api.AUDIT_METHOD_ACTIONS.get(
			(context.get(audit_api.AUDIT_DETAIL_METHOD) or '').lower(), AUDIT_ACTION_READ)

	return audit_api.AUDIT_EVENT_ACTIONS.get(event_type, audit_api.AUDIT_ACTION_EXECUTE)


def coding(code_display, system):
	'''	Build a FHIR Coding dict from a (code, display) pair.
	'''
	code, display = code_display
	return {'system': system, 'code': code, 'display': display}


def build_audit_event(event_type, user=None, outcome=True, request=None, server=None,
		entity_id=None, context=None, outcome_desc=None, recorded=None):
	'''	Build a FHIR R4B `AuditEvent` for a Sonador audit event.

		@input event_type (str): one of the `apisettings.AUDIT_*` event constants
		@input user (User | str | None): the acting identity
		@input outcome (bool): True when the action was granted/succeeded
		@input request (HttpRequest, default=None): source of the client address
		@input server (PacsImagingServer, default=None): imaging server context
		@input entity_id (str, default=None): primary resource identifier
		@input context (dict, default=None): `entity.detail` name/value pairs
		@input outcome_desc (str, default=None): `AuditEvent.outcomeDesc`
		@input recorded (datetime, default=None): defaults to `timezone.now()`

		@returns dict: the validated AuditEvent, JSON-ready
	'''
	context = dict(context or {})

	# Strip any query string before the record is built. Emit sites are expected to pass a
	# sanitized URI already, but this is the boundary every record passes through, so doing
	# it here means no caller can leak demographics by forgetting. Parameter names are
	# retained, values never are.
	if context.get(audit_api.AUDIT_DETAIL_URI):
		_path, _query_keys = sanitize_uri(context[audit_api.AUDIT_DETAIL_URI])
		context[audit_api.AUDIT_DETAIL_URI] = _path

		if _query_keys and not context.get(audit_api.AUDIT_DETAIL_QUERY_KEYS):
			context[audit_api.AUDIT_DETAIL_QUERY_KEYS] = _query_keys

	type_coding, subtype_coding = audit_event_codes(event_type, context=context)
	username, alt_id = resolve_actor(user)

	# The imaging server is context on every event that has one, so it is recorded as a
	# detail rather than left to the caller to remember.
	if server is not None and not context.get(audit_api.AUDIT_DETAIL_IMAGING_SERVER):
		context[audit_api.AUDIT_DETAIL_IMAGING_SERVER] = server_audit_label(server)

	# Requesting agent. `who.identifier` carries the username rather than a Reference to a
	# Patient/Practitioner resource: Sonador users are not FHIR resources, and an
	# identifier is what a downstream audit repository can correlate on.
	agent = {
		'who': {'identifier': {'value': username}},
		'requestor': True,
	}

	if alt_id:
		agent['altId'] = alt_id

	address = client_address(request)
	if address:
		agent['network'] = {'address': address, 'type': audit_api.AUDIT_NETWORK_TYPE_IP}

	# Second agent: the application that made the decision. R4B expects the responsible
	# party as well as the requestor, and this is what distinguishes a Sonador-mediated
	# access from a direct one.
	agents = [agent, {
		'who': {'display': SONADOR_USER_LABEL},
		'requestor': False,
	}]

	source_site = gsetting('AUDIT_SOURCE_SITE') or 'sonador'
	source = {
		'site': source_site,
		'observer': {'display': source_site},
		'type': [coding(audit_api.SECURITY_SOURCE_TYPE_APPLICATION_SERVER,
			audit_api.SECURITY_SOURCE_TYPE_SYSTEM)],
	}

	event = {
		'resourceType': 'AuditEvent',
		'type': coding(type_coding, audit_api.DCM_SYSTEM),
		'action': audit_event_action(event_type, context=context),
		'recorded': recorded or timezone.now(),
		'outcome': audit_api.AUDIT_OUTCOME_SUCCESS if outcome else audit_api.AUDIT_OUTCOME_MINOR_FAILURE,
		'agent': agents,
		'source': source,
	}

	if subtype_coding:
		event['subtype'] = [coding(subtype_coding, audit_api.DCM_SYSTEM)]

	if outcome_desc:
		event['outcomeDesc'] = outcome_desc

	# Entity: what was acted on. Details are string pairs, so every value is coerced --
	# validity and group ids arrive as integers.
	entity = {}

	if entity_id:
		entity['what'] = {'identifier': {'value': str(entity_id)}}

	if event_type in audit_api.AUDIT_PHI_EVENT_TYPES:
		entity['securityLabel'] = [coding(audit_api.CONFIDENTIALITY_RESTRICTED,
			audit_api.CONFIDENTIALITY_SYSTEM)]

	detail = [{'type': str(name), 'valueString': str(value)}
		for name, value in context.items() if value not in (None, '')]

	if detail:
		entity['detail'] = detail

	if entity:
		event['entity'] = [entity]

	# Validate through the model, then hand back a JSON-ready dict. Serialization happens
	# exactly once -- the producer encodes this dict to bytes and does not re-encode an
	# already-serialized string.
	return AuditEvent(**event).model_dump(mode='json', exclude_none=True)
