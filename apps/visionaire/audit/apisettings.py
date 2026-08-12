'''	Constants for the Sonador audit trail: event types, DCM vocabulary codes, and the
	names of the key/value pairs carried on `AuditEvent.entity[0].detail`.

	Adding a new audit event means adding a constant here and an entry in
	`AUDIT_EVENT_CODES` -- not a new signal and not a new topic. The platform runs exactly
	two Kafka producers, each owning one topic and discriminating message kinds by an
	in-payload field: `orthanc-index` from the Orthanc plugin, `sonador-audit-event` from
	the web application.
'''
from guru import apisettings as gapi
from orthancapi import apisettings as orthanc_api
from wgtauth.services.apisettings import API_ACCESS_APITOKEN_QSPARAM


# Audit event types
#
# The value of each constant is what identifies the event inside Sonador; the DCM codes
# it maps to in `AUDIT_EVENT_CODES` are what make the record intelligible to an external
# audit repository.
AUDIT_RESOURCE_ACCESS = 'resource-access'
AUDIT_RESOURCE_ACCESS_CACHED = 'resource-access-cached'
AUDIT_USER_LOGIN = 'user-login'
AUDIT_USER_LOGIN_FAILED = 'user-login-failed'
AUDIT_USER_LOGOUT = 'user-logout'
AUDIT_ACL_GRANT = 'acl-grant'
AUDIT_ACL_MODIFY = 'acl-modify'
AUDIT_ACL_REVOKE = 'acl-revoke'
AUDIT_CREDENTIAL_ISSUE = 'credential-issue'
AUDIT_CREDENTIAL_REVOKE = 'credential-revoke'

AUDIT_EVENT_TYPES = set((
	AUDIT_RESOURCE_ACCESS, AUDIT_RESOURCE_ACCESS_CACHED,
	AUDIT_USER_LOGIN, AUDIT_USER_LOGIN_FAILED, AUDIT_USER_LOGOUT,
	AUDIT_ACL_GRANT, AUDIT_ACL_MODIFY, AUDIT_ACL_REVOKE,
	AUDIT_CREDENTIAL_ISSUE, AUDIT_CREDENTIAL_REVOKE,
))

# Events which can carry a reference to a patient's imaging data. Records for these
# events are labelled "restricted" so a downstream consumer can route them under a
# stricter policy than a login record. The identifier is recorded; the DICOM content
# behind it never is.
AUDIT_PHI_EVENT_TYPES = set((AUDIT_RESOURCE_ACCESS, AUDIT_RESOURCE_ACCESS_CACHED))


# Code systems
#
# DCM is the audit vocabulary shared by the DICOM audit trail message profile and IHE
# ATNA, and is the system bound by the FHIR `audit-event-type` ValueSet.
DCM_SYSTEM = 'http://dicom.nema.org/resources/ontology/DCM'
SECURITY_SOURCE_TYPE_SYSTEM = 'http://terminology.hl7.org/CodeSystem/security-source-type'
CONFIDENTIALITY_SYSTEM = 'http://terminology.hl7.org/CodeSystem/v3-Confidentiality'


# DCM audit event codes.
#
# Each code and its display label is declared as its own string constant, and the pair is
# then combined into the `DCM_*` tuple the record builder consumes. This follows the
# convention the Sonador IO client uses for DICOM constants (`apisettings.base`, where
# `DCMCODE_PATIENT_ID` and `DCMHEADER_PATIENT_ID` are declared as siblings): the code and
# the label can each be referenced by name and reached by autocomplete, instead of being
# addressed positionally as `DCM_QUERY[0]` and `DCM_QUERY[1]`.

# Type codes
DCMCODE_DICOM_INSTANCES_ACCESSED = '110103'
DCMLABEL_DICOM_INSTANCES_ACCESSED = 'DICOM Instances Accessed'

DCMCODE_DICOM_STUDY_DELETED = '110105'
DCMLABEL_DICOM_STUDY_DELETED = 'DICOM Study Deleted'

DCMCODE_EXPORT = '110106'
DCMLABEL_EXPORT = 'Export'

DCMCODE_IMPORT = '110107'
DCMLABEL_IMPORT = 'Import'

DCMCODE_QUERY = '110112'
DCMLABEL_QUERY = 'Query'

DCMCODE_SECURITY_ALERT = '110113'
DCMLABEL_SECURITY_ALERT = 'Security Alert'

DCMCODE_USER_AUTHENTICATION = '110114'
DCMLABEL_USER_AUTHENTICATION = 'User Authentication'

# Sub-type codes
DCMCODE_LOGIN = '110122'
DCMLABEL_LOGIN = 'Login'

DCMCODE_LOGOUT = '110123'
DCMLABEL_LOGOUT = 'Logout'

DCMCODE_SECURITY_ROLES_CHANGED = '110136'
DCMLABEL_SECURITY_ROLES_CHANGED = 'Security Roles Changed'

DCMCODE_USER_SECURITY_ATTRIBUTES_CHANGED = '110137'
DCMLABEL_USER_SECURITY_ATTRIBUTES_CHANGED = 'User security Attributes Changed'

# Source type: Sonador is an application server, not a device or a user interface.
SECURITY_SOURCE_TYPE_CODE_APPLICATION_SERVER = '4'
SECURITY_SOURCE_TYPE_LABEL_APPLICATION_SERVER = 'Application Server'

# Confidentiality label applied to PHI-bearing records.
CONFIDENTIALITY_CODE_RESTRICTED = 'R'
CONFIDENTIALITY_LABEL_RESTRICTED = 'restricted'


# Unified (code, label) representations, as consumed by the record builder.
DCM_DICOM_INSTANCES_ACCESSED = (DCMCODE_DICOM_INSTANCES_ACCESSED, DCMLABEL_DICOM_INSTANCES_ACCESSED)
DCM_DICOM_STUDY_DELETED = (DCMCODE_DICOM_STUDY_DELETED, DCMLABEL_DICOM_STUDY_DELETED)
DCM_EXPORT = (DCMCODE_EXPORT, DCMLABEL_EXPORT)
DCM_IMPORT = (DCMCODE_IMPORT, DCMLABEL_IMPORT)
DCM_QUERY = (DCMCODE_QUERY, DCMLABEL_QUERY)
DCM_SECURITY_ALERT = (DCMCODE_SECURITY_ALERT, DCMLABEL_SECURITY_ALERT)
DCM_USER_AUTHENTICATION = (DCMCODE_USER_AUTHENTICATION, DCMLABEL_USER_AUTHENTICATION)

DCM_LOGIN = (DCMCODE_LOGIN, DCMLABEL_LOGIN)
DCM_LOGOUT = (DCMCODE_LOGOUT, DCMLABEL_LOGOUT)
DCM_SECURITY_ROLES_CHANGED = (DCMCODE_SECURITY_ROLES_CHANGED, DCMLABEL_SECURITY_ROLES_CHANGED)
DCM_USER_SECURITY_ATTRIBUTES_CHANGED = (
	DCMCODE_USER_SECURITY_ATTRIBUTES_CHANGED, DCMLABEL_USER_SECURITY_ATTRIBUTES_CHANGED)

SECURITY_SOURCE_TYPE_APPLICATION_SERVER = (
	SECURITY_SOURCE_TYPE_CODE_APPLICATION_SERVER, SECURITY_SOURCE_TYPE_LABEL_APPLICATION_SERVER)
CONFIDENTIALITY_RESTRICTED = (CONFIDENTIALITY_CODE_RESTRICTED, CONFIDENTIALITY_LABEL_RESTRICTED)


# Event type -> (type coding, subtype coding). A `None` subtype is omitted from the
# record rather than serialized as null.
#
# The two resource-access events are absent: their type code depends on what the request
# actually does (read, query, export, import, delete) and is derived per-request by
# `fhir.resource_access_type_code`.
AUDIT_EVENT_CODES = {
	AUDIT_USER_LOGIN: (DCM_USER_AUTHENTICATION, DCM_LOGIN),
	AUDIT_USER_LOGIN_FAILED: (DCM_USER_AUTHENTICATION, DCM_LOGIN),
	AUDIT_USER_LOGOUT: (DCM_USER_AUTHENTICATION, DCM_LOGOUT),
	AUDIT_ACL_GRANT: (DCM_SECURITY_ALERT, DCM_SECURITY_ROLES_CHANGED),
	AUDIT_ACL_MODIFY: (DCM_SECURITY_ALERT, DCM_SECURITY_ROLES_CHANGED),
	AUDIT_ACL_REVOKE: (DCM_SECURITY_ALERT, DCM_SECURITY_ROLES_CHANGED),
	AUDIT_CREDENTIAL_ISSUE: (DCM_USER_AUTHENTICATION, DCM_USER_SECURITY_ATTRIBUTES_CHANGED),
	AUDIT_CREDENTIAL_REVOKE: (DCM_USER_AUTHENTICATION, DCM_USER_SECURITY_ATTRIBUTES_CHANGED),
}


# AuditEvent.action -- the type of change the event records.
AUDIT_ACTION_CREATE = 'C'
AUDIT_ACTION_READ = 'R'
AUDIT_ACTION_UPDATE = 'U'
AUDIT_ACTION_DELETE = 'D'
AUDIT_ACTION_EXECUTE = 'E'

# HTTP method -> AuditEvent.action, for the resource-access events. Requests that are
# neither a write nor a delete are a read.
# The authorization plugin sends the verb lowercased, so the shared constants are lowered
# rather than restated as literals.
AUDIT_METHOD_POST = gapi.HTTP_POST.lower()
AUDIT_METHOD_GET = gapi.HTTP_GET.lower()
AUDIT_METHOD_PUT = gapi.HTTP_PUT.lower()
AUDIT_METHOD_PATCH = gapi.HTTP_PATCH.lower()
AUDIT_METHOD_DELETE = gapi.HTTP_DELETE.lower()

AUDIT_METHOD_ACTIONS = {
	AUDIT_METHOD_POST: AUDIT_ACTION_CREATE,
	AUDIT_METHOD_GET: AUDIT_ACTION_READ,
	AUDIT_METHOD_PUT: AUDIT_ACTION_UPDATE,
	AUDIT_METHOD_PATCH: AUDIT_ACTION_UPDATE,
	AUDIT_METHOD_DELETE: AUDIT_ACTION_DELETE,
}

# Event type -> AuditEvent.action, for the events whose action does not come from an
# HTTP method. Identity events execute rather than change a resource.
AUDIT_EVENT_ACTIONS = {
	AUDIT_USER_LOGIN: AUDIT_ACTION_EXECUTE,
	AUDIT_USER_LOGIN_FAILED: AUDIT_ACTION_EXECUTE,
	AUDIT_USER_LOGOUT: AUDIT_ACTION_EXECUTE,
	AUDIT_ACL_GRANT: AUDIT_ACTION_CREATE,
	AUDIT_ACL_MODIFY: AUDIT_ACTION_UPDATE,
	AUDIT_ACL_REVOKE: AUDIT_ACTION_DELETE,
	AUDIT_CREDENTIAL_ISSUE: AUDIT_ACTION_CREATE,
	AUDIT_CREDENTIAL_REVOKE: AUDIT_ACTION_DELETE,
}


# AuditEvent.outcome. R4B constrains this to the DICOM outcome codes; a denied
# authorization is a minor failure, not a system failure, so it is 4 rather than 8.
AUDIT_OUTCOME_SUCCESS = '0'
AUDIT_OUTCOME_MINOR_FAILURE = '4'


# Network type on AuditEvent.agent.network -- 2 is "IP Address".
AUDIT_NETWORK_TYPE_IP = '2'


# `entity[0].detail` key names. The FHIR detail element is an untyped list of
# name/value pairs, so these names are the whole contract a consumer parses against.
# Keep them stable.
AUDIT_DETAIL_ORTHANC_ID = 'OrthancId'
AUDIT_DETAIL_DICOM_UID = 'DicomUid'
AUDIT_DETAIL_LEVEL = 'Level'
AUDIT_DETAIL_METHOD = 'Method'
AUDIT_DETAIL_URI = 'Uri'

# Names of the query-string parameters a request carried. The names only -- the values are
# dropped at the audit boundary, because a DICOMweb search routinely filters on patient
# demographics and those must never enter the record.
AUDIT_DETAIL_QUERY_KEYS = 'QueryKeys'
AUDIT_DETAIL_ACTION = 'Action'
AUDIT_DETAIL_IMAGING_SERVER = 'ImagingServer'
AUDIT_DETAIL_VALIDITY = 'Validity'
AUDIT_DETAIL_TOKEN_KEY = 'TokenKey'
AUDIT_DETAIL_CACHE_HIT = 'CacheHit'
# The group detail names the same thing the imaging server API already calls a group, so it
# reuses that constant rather than restating the string.
AUDIT_DETAIL_GROUP = orthanc_api.IMAGING_SERVER_RESOURCE_GROUP
AUDIT_DETAIL_RESOURCE_SCOPE = 'ResourceScope'
AUDIT_DETAIL_PERMISSIONS = 'Permissions'
AUDIT_DETAIL_SUBJECT_USER = 'SubjectUser'
AUDIT_DETAIL_CREDENTIAL_TYPE = 'CredentialType'

# Credential kinds recorded on `CredentialType`. The token kind is the credential name the
# platform already uses on the wire (`wgtauth.services.apisettings`), so a consumer
# correlating audit records against request logs sees the same spelling in both.
AUDIT_CREDENTIAL_TYPE_TOKEN = API_ACCESS_APITOKEN_QSPARAM
AUDIT_CREDENTIAL_TYPE_ACCESS_KEY = 'access-id-secret'


# Actor recorded when the request carries no resolvable identity. A denial of an
# unauthenticated request is exactly the event a reviewer most wants to see, so the
# record is still written with a placeholder rather than dropped.
AUDIT_ACTOR_UNKNOWN = 'unknown'


# Resource-access classification. These mirror the URI branches already resolved by
# `OrthancServiceAuthorizationForm.clean_auth_request`; the audit path reads the
# cleaned fields and these shared constants rather than re-parsing the URI.
AUDIT_URI_ARCHIVE = orthanc_api.ORTHANC_RESOURCE_ARCHIVE
AUDIT_URI_INSTANCES = orthanc_api.ORTHANC_INSTANCES
AUDIT_URI_TOOLS_FIND = orthanc_api.ORTHANC_TOOLS_FIND
AUDIT_URI_TOOLS_FIND_SECURE = orthanc_api.ORTHANC_TOOLS_FIND_SECURE


# URI sanitization
#
# The request URI is client-supplied all the way down, so nothing in it can be trusted to
# be free of patient demographics. Rather than trying to detect PHI -- which cannot be done
# reliably -- both halves of the URI are reduced to values drawn from a closed set:
#
#   * a path segment is kept only if it is a known route token or matches a strict
#     identifier shape; anything else becomes a placeholder;
#   * a query parameter *name* is kept only if it is a recognized DICOM or QIDO search key;
#     anything else is counted rather than named.
#
# Query parameter *values* are never recorded under any circumstances.

# Placeholder substituted for a path segment that is neither a route token nor an identifier.
AUDIT_URI_SEGMENT_PLACEHOLDER = '{id}'

# How unrecognized query parameters are summarized, so a reviewer can tell that a search
# carried filters beyond the ones named and pivot to the request logs for the detail.
AUDIT_QUERY_KEYS_UNLISTED = '+%d unlisted'

# Route tokens that may appear in a recorded path. Built from the endpoint constants the
# authorization path already uses, plus the DICOMweb sub-resources that appear as bare path
# segments. A token missing from this set is only a cosmetic loss -- the segment renders as
# the placeholder -- but the tokens the §5.5 type classification greps for (archive,
# instances, tools/find) must remain present.
AUDIT_URI_ROUTE_TOKENS = frozenset(_t.strip('/').lower() for _t in (
	orthanc_api.ORTHANC_DICOMWEB, orthanc_api.ORTHANC_DICOMWEB_INTERNAL,
	orthanc_api.ORTHANC_SYSTEM, orthanc_api.ORTHANC_INSTANCES,
	orthanc_api.ORTHANC_RESOURCE_PATIENT, orthanc_api.ORTHANC_RESOURCE_STUDY,
	orthanc_api.ORTHANC_RESOURCE_SERIES, orthanc_api.ORTHANC_RESOURCE_INSTANCE,
	orthanc_api.ORTHANC_RESOURCE_WORKLIST, orthanc_api.ORTHANC_RESOURCE_COMMENT,
	orthanc_api.ORTHANC_RESOURCE_ARCHIVE, orthanc_api.ORTHANC_RESOURCE_MANAGE,
	orthanc_api.ORTHANC_RESOURCE_GROUP, orthanc_api.ORTHANC_RESOURCE_STUDY_PLURAL,
) if _t) | frozenset((
	'patients', 'series', 'instances', 'studies', 'groups', 'comments', 'worklist',
	'metadata', 'rendered', 'thumbnail', 'frames', 'bulk', 'wado', 'wado-rs', 'wado-uri',
	'tools', 'find', 'secure-find', 'cache', 'dcm-tags', 'tags', 'acl', 'resource-acl',
	'user', 'users', 'group', 'ohif', 'statistics', 'attachments', 'preview',
	'distortion-filter', 'devices', 'export', 'download', 'shared', 'app', 'static',
))

# Path segments that are safe to record verbatim because their shape cannot carry a name:
# a DICOM UID is digits and dots, an Orthanc resource id is dash-separated hex, and a bare
# integer is a group or frame index.
AUDIT_URI_DICOM_UID_PATTERN = r'^[0-9][0-9.]*$'
AUDIT_URI_ORTHANC_ID_PATTERN = r'^[0-9a-f]{8}(?:-[0-9a-f]{8})+$'
AUDIT_URI_INDEX_PATTERN = r'^[0-9]+$'

AUDIT_URI_IDENTIFIER_PATTERNS = (
	AUDIT_URI_DICOM_UID_PATTERN, AUDIT_URI_ORTHANC_ID_PATTERN, AUDIT_URI_INDEX_PATTERN)

# Query parameter names that may be recorded. The DICOM attributes QIDO-RS accepts as
# search keys (PS3.18 §10.6), plus the QIDO and Orthanc control parameters. Recording that a
# search filtered on PatientID is what makes the trail useful to a reviewer; the name alone
# identifies nobody, and anything not on this list is counted instead of named.
AUDIT_QUERY_KEY_ALLOWLIST = frozenset(_k.lower() for _k in (
	# QIDO-RS and Orthanc control parameters
	'limit', 'offset', 'fuzzymatching', 'includefield', 'expand', 'requestedTags',
	'orderby', 'since', 'count',

	# Study-level matching keys
	'StudyDate', 'StudyTime', 'AccessionNumber', 'ModalitiesInStudy',
	'ReferringPhysicianName', 'PatientName', 'PatientID', 'StudyInstanceUID', 'StudyID',
	'NumberOfStudyRelatedSeries', 'NumberOfStudyRelatedInstances', 'StudyDescription',
	'PatientBirthDate', 'PatientSex', 'IssuerOfPatientID',

	# Series-level matching keys
	'Modality', 'SeriesInstanceUID', 'SeriesNumber', 'SeriesDescription',
	'PerformedProcedureStepStartDate', 'PerformedProcedureStepStartTime',
	'RequestAttributesSequence', 'ScheduledProcedureStepID', 'RequestedProcedureID',
	'BodyPartExamined',

	# Instance-level matching keys
	'SOPClassUID', 'SOPInstanceUID', 'InstanceNumber', 'Rows', 'Columns',
	'BitsAllocated', 'NumberOfFrames',
))


# Kafka delivery. `flush()` is called only at process shutdown -- never on the request
# path -- so this bounds how long interpreter exit can block on an unreachable broker.
AUDIT_FLUSH_TIMEOUT_DEFAULT = 5.0
