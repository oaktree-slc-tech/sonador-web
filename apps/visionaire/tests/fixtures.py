'''	Test fixtures for the User Preferences API, built from the viewer's real 0.4
	defaults (issue #42 §5.1) so the backend is validated against the exact shapes the
	frontend produces:

	* hotkeys           -- `hotkeys` array in `apps/visionaire/templates/ohif/sonador.app-config.json`
	                       (converted to the commandName -> {label, keys} map the panel stores)
	* window-level      -- `defaultState.windowLevelData` in the `preferences` redux reducer
	* viewer-metadata   -- initial state of `useViewerMetadataSettingsStore`
	* study-list        -- `DEFAULT_FILTERS` / `DEFAULT_COLUMNS_IDS` / `WORK_LIST_DEFAULT_COLUMNS_IDS`
	                       in `platform/viewer/src/lib/constants.js`
'''
from ..models.userpref import CURRENT_PREF_VERSION, LEGACY_PREF_VERSION

CURRENT_VERSION = CURRENT_PREF_VERSION      # '0.4'
LEGACY_VERSION = LEGACY_PREF_VERSION        # '0.3'


# -- General ---------------------------------------------------------------------------

DEFAULT_GENERAL = {'language': 'en-US'}


# -- Hotkeys (full default set from sonador.app-config.json) ----------------------------

DEFAULT_HOTKEYS = {
	'incrementActiveViewport': {'label': 'Next Viewport', 'keys': ['right']},
	'decrementActiveViewport': {'label': 'Previous Viewport', 'keys': ['left']},
	'rotateViewportCW': {'label': 'Rotate Right', 'keys': ['r']},
	'rotateViewportCCW': {'label': 'Rotate Left', 'keys': ['l']},
	'invertViewport': {'label': 'Invert', 'keys': ['i']},
	'flipViewportVertical': {'label': 'Flip Horizontally', 'keys': ['h']},
	'flipViewportHorizontal': {'label': 'Flip Vertically', 'keys': ['v']},
	'scaleUpViewport': {'label': 'Zoom In', 'keys': ['+']},
	'scaleDownViewport': {'label': 'Zoom Out', 'keys': ['-']},
	'fitViewportToWindow': {'label': 'Zoom to Fit', 'keys': ['=']},
	'resetViewport': {'label': 'Reset', 'keys': ['space']},
	'nextImage': {'label': 'Next Image', 'keys': ['down']},
	'previousImage': {'label': 'Previous Image', 'keys': ['up']},
	'previousViewportDisplaySet': {'label': 'Previous Series', 'keys': ['pagedown']},
	'nextViewportDisplaySet': {'label': 'Next Series', 'keys': ['pageup']},
	'setZoomTool': {'label': 'Zoom', 'keys': ['z']},
	'windowLevelPreset1': {'label': 'W/L Preset 1', 'keys': ['1']},
	'windowLevelPreset2': {'label': 'W/L Preset 2', 'keys': ['2']},
	'windowLevelPreset3': {'label': 'W/L Preset 3', 'keys': ['3']},
	'windowLevelPreset4': {'label': 'W/L Preset 4', 'keys': ['4']},
	'windowLevelPreset5': {'label': 'W/L Preset 5', 'keys': ['5']},
	'windowLevelPreset6': {'label': 'W/L Preset 6', 'keys': ['6']},
	'windowLevelPreset7': {'label': 'W/L Preset 7', 'keys': ['7']},
	'windowLevelPreset8': {'label': 'W/L Preset 8', 'keys': ['8']},
	'windowLevelPreset9': {'label': 'W/L Preset 9', 'keys': ['9']},
}


# -- Window level (the 10 default presets; keys are strings in JSON) --------------------

DEFAULT_WINDOW_LEVEL = {
	'1': {'description': 'Soft tissue', 'window': '550', 'level': '40'},
	'2': {'description': 'Lung', 'window': '150', 'level': '-600'},
	'3': {'description': 'Liver', 'window': '150', 'level': '90'},
	'4': {'description': 'Bone', 'window': '2500', 'level': '480'},
	'5': {'description': 'Brain', 'window': '80', 'level': '40'},
	'6': {'description': 'Trest', 'window': '1', 'level': '1'},
	'7': {'description': '', 'window': '', 'level': ''},
	'8': {'description': '', 'window': '', 'level': ''},
	'9': {'description': '', 'window': '', 'level': ''},
	'10': {'description': '', 'window': '', 'level': ''},
}


# -- Viewer metadata (four-corner overlay; store initial state) -------------------------

DEFAULT_VIEWER_METADATA = {
	'topLeftCorner': [
		{'title': 'Patient Name', 'value': 'patientName'},
		{'title': 'Patient Id', 'value': 'patientId'},
	],
	'topRightCorner': [
		{'title': 'Study Description', 'value': 'studyDescription'},
		{'title': 'Study Date Time', 'value': 'studyDate-studyTime'},
	],
	'bottomLeftCorner': [
		{'title': 'Series Number', 'value': 'seriesNumber'},
		{'title': 'Img instance number index/stack size', 'value': 'Img-instance-number-index-stack-size'},
		{'title': 'Frame Rate Image Info', 'value': 'frameRate-image-info'},
	],
	'bottomRightCorner': [
		{'title': 'Zoom Percentage', 'value': 'zoomPercentage'},
		{'title': 'WWWC', 'value': 'wwwc'},
		{'title': 'Compression', 'value': 'compression'},
	],
}


# -- Study list (defaults from lib/constants.js) ----------------------------------------

DEFAULT_FILTERS = ['PatientBirthDate', 'PatientID', 'Modality', 'StudyDescription', 'SeriesDescription']
DEFAULT_COLUMNS_IDS = ['PatientName', 'PatientID', 'AccessionNumber', 'StudyDate', 'modalities', 'StudyDescription']
WORK_LIST_DEFAULT_COLUMNS_IDS = [
	'AssignedUser', 'GroupName', 'PatientName', 'Status', 'ReasonForReview',
	'mrn', 'AccessionNumber', 'StudyDate', 'modalities', 'series', 'StudyDescription',
]
COLUMN_ORDER_EXPANDER = 'selector-settings-expander'

DEFAULT_STUDYLIST = {
	'worklist': {
		'selectedFilters': list(DEFAULT_FILTERS),
		'selectedColumns': list(WORK_LIST_DEFAULT_COLUMNS_IDS),
		'columnOrder': [COLUMN_ORDER_EXPANDER] + list(WORK_LIST_DEFAULT_COLUMNS_IDS),
	},
	'allStudies': {
		'selectedFilters': list(DEFAULT_FILTERS),
		'selectedColumns': list(DEFAULT_COLUMNS_IDS),
		'columnOrder': [COLUMN_ORDER_EXPANDER] + list(DEFAULT_COLUMNS_IDS),
	},
	'shared': {
		'selectedFilters': list(DEFAULT_FILTERS),
		'selectedColumns': list(DEFAULT_COLUMNS_IDS),
		'columnOrder': [COLUMN_ORDER_EXPANDER] + list(DEFAULT_COLUMNS_IDS),
	},
	'upload': {
		'selectedColumns': list(DEFAULT_COLUMNS_IDS),
		'columnOrder': [COLUMN_ORDER_EXPANDER] + list(DEFAULT_COLUMNS_IDS),
	},
}


# -- Full 0.4 documents (§5.1 shapes) ---------------------------------------------------

def viewer_document(version=CURRENT_VERSION):
	'''	A complete `UserPref.viewer` document for `version` with all four sections.
	'''
	return {
		version: {
			'general': dict(DEFAULT_GENERAL),
			'hotkeys': dict(DEFAULT_HOTKEYS),
			'windowLevel': dict(DEFAULT_WINDOW_LEVEL),
			'viewerMetadata': dict(DEFAULT_VIEWER_METADATA),
		}
	}


def studylist_document(version=CURRENT_VERSION):
	'''	A complete `UserPref.studylist` document for `version` with all four interfaces.
	'''
	return {version: {interface: dict(slice_) for interface, slice_ in DEFAULT_STUDYLIST.items()}}


# Section key -> default `values` payload, for the viewer section endpoints.
VIEWER_SECTION_DEFAULTS = {
	'general': DEFAULT_GENERAL,
	'hotkeys': DEFAULT_HOTKEYS,
	'windowLevel': DEFAULT_WINDOW_LEVEL,
	'viewerMetadata': DEFAULT_VIEWER_METADATA,
}


# -- Authorization server --------------------------------------------------------------

def create_authserver(callback_url='', **kwargs):
	'''	Create a SocialAuthorizationServer (and the SocialAppProvider it requires) for tests
		which exercise redirect validation against the registered client callback URLs.

		`get_default_authserver` returns the only row when exactly one exists, so a single call
		is enough to make this the auth server the logout endpoint validates against.
	'''
	from wgtauth.social.models import SocialAppProvider
	from ..auth.models import SocialAuthorizationServer

	provider = SocialAppProvider.objects.create(
		name=kwargs.pop('provider_name', 'Test Connect'),
		hostname='idp.example.com', port=443, scheme='https',
		login_class='', endpoint_authorization='/o/authorize/', endpoint_token='/o/token/',
		endpoint_token_revoke='/o/revoke_token/', endpoint_user='/o/introspect/')

	return SocialAuthorizationServer.objects.create(
		provider=provider,
		description=kwargs.pop('description', 'Test authorization server'),
		client_id=kwargs.pop('client_id', 'test-client-id'),
		client_secret=kwargs.pop('client_secret', 'test-client-secret'),
		callback_url=callback_url,
		**kwargs)
