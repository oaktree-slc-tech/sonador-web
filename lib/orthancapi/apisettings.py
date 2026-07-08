'''	Constants and values used by the Orthanc API module
'''
import re

# Orthanc Imaging Server Resources
IMAGING_SERVER_RESOURCE_PATIENT = 'Patient'
IMAGING_SERVER_RESOURCE_STUDY = 'Study'
IMAGING_SERVER_RESOURCE_SERIES = 'Series'
IMAGING_SERVER_RESOURCE_IMAGE = 'Instance'
IMAGING_SERVER_RESOURCE_REPORT = 'Report'
IMAGING_SERVER_RESOURCE_WORKLIST = 'Worklist'
IMAGING_SERVER_RESOURCE_COMMENT = 'Comment'
IMAGING_SERVER_RESOURCE_GROUP = 'Group'
IMAGING_SERVER_RESOURCE_TAG = 'Tag'
IMAGING_SERVER_RESOURCE_DISTORTION_FILTER_DEVICE = 'Distortion-Filter/Device'

IMAGING_SERVER_RESOURCES = set((
	IMAGING_SERVER_RESOURCE_PATIENT, 
	IMAGING_SERVER_RESOURCE_STUDY, 
	IMAGING_SERVER_RESOURCE_SERIES, 
	IMAGING_SERVER_RESOURCE_IMAGE
))

IMAGING_SERVER_LAST_UPDATE = 'LastUpdate'
IMAGING_SERVER_MODIFIED = 'Modified'
IMAGING_SERVER_STABLE = 'IsStable'
IMAGING_SERVER_MAINDICOM = 'MainDicomTags'
IMAGING_SERVER_PATIENT_MAINDICOM = 'PatientMainDicomTags'
IMAGING_SERVER_DICOMTAGS_SIGNATURE = 'MainDicomTagsSignature'
IMAGING_SERVER_PARENT_PATIENT = 'ParentPatient'
IMAGING_SERVER_PARENT_STUDY = 'ParentStudy'
IMAGING_SERVER_REQUESTED_TAGS = 'RequestedTags'


# Orthanc Resource Shortcodes
ORTHANC_RESOURCE_PATIENT = IMAGING_SERVER_RESOURCE_PATIENT.lower()
ORTHANC_RESOURCE_STUDY = IMAGING_SERVER_RESOURCE_STUDY.lower()
ORTHANC_RESOURCE_SERIES = IMAGING_SERVER_RESOURCE_SERIES.lower()
ORTHANC_RESOURCE_INSTANCE = IMAGING_SERVER_RESOURCE_IMAGE.lower()
ORTHANC_RESOURCE_WORKLIST = IMAGING_SERVER_RESOURCE_WORKLIST.lower()
ORTHANC_RESOURCE_COMMENT = IMAGING_SERVER_RESOURCE_COMMENT.lower()
ORTHANC_RESOURCE_ARCHIVE = 'archive'

ORTHANC_LOCALAUTH_RESOURCES = set((
	ORTHANC_RESOURCE_PATIENT,
	ORTHANC_RESOURCE_STUDY, 
	ORTHANC_RESOURCE_SERIES,
	ORTHANC_RESOURCE_INSTANCE,
))

ORTHANC_RESOURCE_STUDY_PLURAL = 'studies'
ORTHANC_LOCALAUTH_RESOURCES_PLURAL = {
	ORTHANC_RESOURCE_STUDY_PLURAL: ORTHANC_RESOURCE_STUDY,
}


# Sonador Server/Group Permissions
SONADOR_PERM_QUERY = 'query'
SONADOR_PERM_UPLOAD = 'upload'
SONADOR_PERM_WORKLIST = 'worklist'
SONADOR_PERM_TAG = 'tag'
SONADOR_PERM_TAG_MODIFY = 'tag_modify'
SONADOR_PERM_DEVICES_LIST = 'devices_list'
SONADOR_PERM_DEVICES_LIST_MODIFY = 'devices_list_modify'

# Sonador Resource Permissions
SONADOR_PERM_VIEW = 'view'
SONADOR_PERM_MODIFY = 'modify'
SONADOR_PERM_REMOVE = 'remove'
SONADOR_PERM_COMMENT_EDIT = 'comment_edit'
SONADOR_PERM_COMMENT_VIEW = 'comment_view'
SONADOR_PERM_ACL = 'acl'


SONADOR_SERVER_PERMS = (SONADOR_PERM_QUERY, SONADOR_PERM_UPLOAD, SONADOR_PERM_WORKLIST,
	SONADOR_PERM_TAG, SONADOR_PERM_TAG_MODIFY, SONADOR_PERM_DEVICES_LIST, SONADOR_PERM_DEVICES_LIST_MODIFY)
SONADOR_RESOURCE_PERMS = (
	SONADOR_PERM_VIEW, SONADOR_PERM_MODIFY, SONADOR_PERM_REMOVE,
	SONADOR_PERM_COMMENT_EDIT, SONADOR_PERM_COMMENT_VIEW, SONADOR_PERM_ACL,
)

SONADOR_PERMS = SONADOR_SERVER_PERMS + SONADOR_RESOURCE_PERMS


# System Resources
ORTHANC_SYSTEM = 'system'


# System Endpoints
ORTHANC_SYSTEM_ENDPOINT = '/%s' % ORTHANC_SYSTEM


# Resource Endpoints
ORTHANC_INSTANCES = '/instances'
ORTHANC_TOOLS_FIND = '/tools/find'
ORTHANC_TOOLS_FIND_SECURE = '/tools/secure-find'
ORTHANC_TOOLS_BULK_CONTENT = '/tools/bulk-content'


# DICOMweb Endpoints
ORTHANC_DICOMWEB = '/dicom-web'
ORTHANC_DICOMWEB_INTERNAL = '/_dicom-web'
ORTHANC_DICOMWEB_WORKLIST = '%s/worklist' % ORTHANC_DICOMWEB
ORTHANC_DICOMWEB_DISTORTION_FILTER = '%s/distortion-filter' % ORTHANC_DICOMWEB
ORTHANC_DICOMWEB_RESOURCE_TYPE_REGEX_STR = r'(?P<resource_type>[a-z]+)'
ORTHANC_DICOMWEB_RESOURCE_REGEX_STR = r'(?P<uid>(?:\d+\.)*\d+)'
ORTHANC_DICOMWEB_STUDIES = '%s/studies' % ORTHANC_DICOMWEB
ORTHANC_DICOMWEB_SERIES = '%s/series' % ORTHANC_DICOMWEB
ORTHANC_DICOMWEB_RESOURCE_ACL = 'resource-acl'
ORTHANC_WADO = '/wado'

# DICOMweb Study Worklist Endpoint: provides ACL mediated access to worklists which
# have been assigend to the user or to groups with which the user is associated.
ORTHANC_DICOMWEB_WORKLIST_STUDY_QUERY = '%s/studies' % ORTHANC_DICOMWEB_WORKLIST

# DICOMweb Regular Expressions
ORTHANC_DICOMWEB_INTERNAL_SERIES_REGEX_STR = r'%s/studies/(?P<study_uid>(?:\d+\.)*\d+)/%s/%s' % (
	ORTHANC_DICOMWEB_INTERNAL, ORTHANC_DICOMWEB_RESOURCE_TYPE_REGEX_STR, ORTHANC_DICOMWEB_RESOURCE_REGEX_STR)
ORTHANC_DICOMWEB_INTERNAL_SERIES_METADATA_REGEX = re.compile(r'%s/metadata' % ORTHANC_DICOMWEB_INTERNAL_SERIES_REGEX_STR)
ORTHANC_DICOMWEB_INTERNAL_INSTANCE_REGEX = re.compile(
	r'%s/instances/(?P<instance_uid>(?:\d+\.)*\d+)' % ORTHANC_DICOMWEB_INTERNAL_SERIES_REGEX_STR)
ORTHANC_DICOMWEB_INTERNAL_INSTANCE_FRAME_REGEX = re.compile(
	r'%s/instances/(?P<instance_uid>(?:\d+\.)*\d+)/frames/(?P<frame_number>\d+)' % ORTHANC_DICOMWEB_INTERNAL_SERIES_REGEX_STR)

ORTHANC_DICOMWEB_WORKLIST_MANAGEMENT_REGEX = re.compile(
	r"%s/%s/worklists" % (ORTHANC_DICOMWEB_STUDIES, ORTHANC_DICOMWEB_RESOURCE_REGEX_STR))
ORTHANC_DICOMWEB_DOWNLOAD_REGEX = re.compile(
	r'%s/%s/%s/archive' % (ORTHANC_DICOMWEB, ORTHANC_DICOMWEB_RESOURCE_TYPE_REGEX_STR, ORTHANC_DICOMWEB_RESOURCE_REGEX_STR))
ORTHANC_DICOMWEB_COMMENT_REGEX = re.compile(
	r'%s/%s/%s/comments' % (ORTHANC_DICOMWEB, ORTHANC_DICOMWEB_RESOURCE_TYPE_REGEX_STR, ORTHANC_DICOMWEB_RESOURCE_REGEX_STR))
ORTHANC_DICOMWEB_ACL_PERMS_REGEX = re.compile(
	r'%s/%s/%s/%s' % (ORTHANC_DICOMWEB, ORTHANC_DICOMWEB_RESOURCE_TYPE_REGEX_STR,
		ORTHANC_DICOMWEB_RESOURCE_REGEX_STR, ORTHANC_DICOMWEB_RESOURCE_ACL))

# DICOMweb ACL policy-management routes (create/list/get/update/revoke a resource policy
# grant): /dicom-web/{studies|series}/{uid}/acl/{user|group}[/{policy-uid}]. This is a
# DIFFERENT endpoint family from ORTHANC_DICOMWEB_ACL_PERMS_REGEX above (permission
# *lookup*, "resource-acl") -- the plugin's own DICOMweb classification regexes
# (dicomWebStudies_/dicomWebSeries_) recognize neither route, so both arrive as an
# unclassified "system" access and Sonador must re-derive level/dicom_uid itself (see
# clean_auth_request). Deliberately matches only ".../acl/(user|group)", never
# ".../resource-acl" (a single, unrelated token with no "/" before "acl").
ORTHANC_DICOMWEB_ACL_MANAGEMENT_REGEX = re.compile(
	r'%s/%s/%s/acl/(?:user|group)(?:/[0-9a-fA-F-]+)?' % (ORTHANC_DICOMWEB, ORTHANC_DICOMWEB_RESOURCE_TYPE_REGEX_STR,
		ORTHANC_DICOMWEB_RESOURCE_REGEX_STR))

# Path-segment check for an ACL policy-management leaf resource (used by
# ResourceAuthorization.resource_perm as a fallback for the DICOMweb route, which never
# carries the "acl" action token -- see ORTHANC_DICOMWEB_ACL_MANAGEMENT_REGEX above).
# Requires a literal "/acl/" segment boundary so it can never match ".../resource-acl".
ORTHANC_ACL_MANAGEMENT_PATH_REGEX = re.compile(r'/acl/(?:user|group)(?:/|$)')

ORTHANC_DICOMWEB_DISTORTION_FILTER_REGEX = re.compile(
	r'%s/groups/(?P<group_uid>\d+)/distortion-filter/(?P<uid>(?:\d+\.)*\d+)' % ORTHANC_DICOMWEB)


# Orthanc Resource URL roots
ORTHANC_RESOURCE_URL_PATIENT = '/patients'
ORTHANC_RESOURCE_URL_STUDY = '/studies'
ORTHANC_RESOURCE_URL_SERIES = '/series'

ORTHANC_RESOURCE_URL = {
	IMAGING_SERVER_RESOURCE_PATIENT.lower(): ORTHANC_RESOURCE_URL_PATIENT,
	IMAGING_SERVER_RESOURCE_STUDY.lower(): ORTHANC_RESOURCE_URL_STUDY,
	IMAGING_SERVER_RESOURCE_SERIES.lower(): ORTHANC_RESOURCE_URL_SERIES,
}


# Sonador Resource Cache
ORTHANC_CACHE = '/cache'
ORTHANC_CACHE_PATIENT = '%s/patient' % ORTHANC_CACHE
ORTHANC_CACHE_STUDY = '%s/studies' % ORTHANC_CACHE
ORTHANC_CACHE_SERIES = '%s/series' % ORTHANC_CACHE
ORTHANC_CACHE_TAGS = '%s/dcm-tags' % ORTHANC_CACHE


# Comments
ORTHANC_COMMENTS = 'comments'


# Bounded "action" tokens emitted by the Orthanc advanced-authorization plugin.
# The plugin's trusted route parser classifies a request into one of these closed-
# enum tokens and tags EVERY level of the resource hierarchy (patient/study/series/
# instance) with it.  This lets us evaluate a meaningful permission at each level of
# a sub-resource request (e.g. a comment write) instead of falling back to a broad
# "modify" check on the ancestors, which would deny the whole request.
ORTHANC_ACTION_COMMENT = 'comment'
ORTHANC_ACTION_WORKLIST = 'worklist'

# "acl" is emitted by the plugin's route parser for the INTERNAL ACL policy-management
# route only (/{patients|studies|series}/{orthanc-id}/acl/{user|group}[/{policy-uid}]),
# since that route is recognized by the plugin's generic resourcesPattern_ and therefore
# explodes into the full patient -> study -> series hierarchy like comment/worklist. The
# DICOMweb mirror of this route is NOT recognized by the plugin's DICOMweb classification
# regexes, so it never carries this token -- see ORTHANC_ACL_MANAGEMENT_PATH_REGEX for the
# URI-based fallback resource_perm uses to detect that case instead.
ORTHANC_ACTION_ACL = 'acl'


# Wildcard Glob Pattern
WILDCARD = '*'


# "View" resource endpoints
ORTHANC_IMAGING_RESOURCES = set((
	ORTHANC_RESOURCE_PATIENT, ORTHANC_RESOURCE_STUDY, ORTHANC_RESOURCE_SERIES, ORTHANC_RESOURCE_INSTANCE
))

# "Query" resource endpoints
ORTHANC_QUERY_RESOURCES = set((
	ORTHANC_CACHE_TAGS,
))


# Orthanc / Sonador Integration API
ORTHANC_RESOURCE_GROUP = IMAGING_SERVER_RESOURCE_GROUP.lower()
ORTHANC_RESOURCE_TAG = IMAGING_SERVER_RESOURCE_TAG.lower()
ORTHANC_RESOURCE_DISTORTION_FILTER_DEVICE = IMAGING_SERVER_RESOURCE_DISTORTION_FILTER_DEVICE.lower()

# Group Resource Endpoints
ORTHANC_GROUPS_ROOT = '/groups'
ORTHANC_DICOMWEB_GROUPS_ROOT = '%s%s' % (ORTHANC_DICOMWEB, ORTHANC_GROUPS_ROOT)
ORTHANC_GROUPS_ROOT_REGEX = r'^%s' % ORTHANC_GROUPS_ROOT
ORTHANC_GROUP_UID_REGEX_STR = r'%s/(?P<uid>\d+)' % ORTHANC_GROUPS_ROOT
ORTHANC_DICOMWEB_UID_REGEX_STR = r'%s/(?P<uid>\d+)' % ORTHANC_DICOMWEB_GROUPS_ROOT
ORTHANC_GROUP_UID_REGEX = re.compile(ORTHANC_GROUP_UID_REGEX_STR)
ORTHANC_DICOMWEB_GROUP_UID_REGEX = re.compile(ORTHANC_DICOMWEB_UID_REGEX_STR)

# Tags
ORTHANC_GROUP_TAGS_REGEX_STR = r'%s/tags/?$' % ORTHANC_GROUP_UID_REGEX_STR
ORTHANC_GROUP_TAGS_REGEX = re.compile(ORTHANC_GROUP_TAGS_REGEX_STR)


# Orthanc Static Resources
ORTHANC_STATIC_RESOURCES = ('css', 'js', 'ico', 'woff2', 'ttf', 'gif', 'wasm')
ORTHANC_OHIF_ROOT = '/ohif'
ORTHANC_OHIF_VIEWER = '%s/viewer' % ORTHANC_OHIF_ROOT
ORTHANC_OHIF_SEGEDITOR = '%s/segmentation' % ORTHANC_OHIF_ROOT
ORTHANC_OHIF_ASSETS = '%s/assets/' % ORTHANC_OHIF_ROOT
ORTHANC_OHIF_MANIFEST_JSON = '%s/manifest.json' % ORTHANC_OHIF_ROOT



# Orthanc Cache Template. Components:
# 1. Server/application secret (prevents offline guessing of cache keys): identifies
# 	 the application instance and prevents collistion of keys.
# 2. Raw user token: taken from the request data. Identifies the user.
# 3. Auth resource prefix: identifies the view/endpoint for the response.
# 4. Request components: orthanc_id, level, method, resource. Identifies the authorization
#    for the Orthanc resource being requested.
ORTHANC_CREDENTIAL_CACHE_KEY_TEMPLATE = b'%s/"%s"/%s/"%s"'