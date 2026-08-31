from django import forms

from guru.forms.related import GuruCoreDataForm

from core.forms import SonadorBaseForm

from ..models.userpref import UserPref


# Version string accepted by the section endpoints, e.g. `0.4` or `10.12` (AR-2).
PREF_VERSION_REGEX = r'^\d+\.\d+$'

# Viewer-metadata four-corner overlay keys and per-corner item cap (LIMIT_CORNER_ITEMS).
VIEWER_META_CORNERS = ('topLeftCorner', 'topRightCorner', 'bottomLeftCorner', 'bottomRightCorner')
VIEWER_META_CORNER_LIMIT = 10

# Window-level preset keys (`1`..`10`, as JSON object keys are strings).
WINDOW_LEVEL_PRESET_KEYS = frozenset(str(index) for index in range(1, 11))

# Study-list interfaces and the sane bounds enforced on their string arrays (FR-15).
STUDYLIST_INTERFACES = ('worklist', 'allStudies', 'shared', 'upload')
STUDYLIST_ARRAY_FIELDS = ('selectedFilters', 'selectedColumns', 'columnOrder')
STUDYLIST_MAX_ENTRIES = 64
STUDYLIST_MAX_STRING = 128


class UserPrefForm(SonadorBaseForm):
	'''	Whole-document form retained for backward compatibility (FR-5). The section
		endpoints below are the preferred write path; this form binds the user from
		request.user and both JSON documents are optional (AR-6).
	'''
	viewer = forms.JSONField(label='Viewer Preferences JSON', required=False)
	studylist = forms.JSONField(label='List Preferences JSON', required=False)

	class Meta:
		model = UserPref
		fields = ('viewer', 'studylist')


class UserPrefSectionForm(GuruCoreDataForm):
	'''	Base form for a single preference-section POST body: `{ version, values }`.

		`version` selects the release document (AR-2); `values` carries the section
		keyset. Subclasses enforce the §5.1 shape of `values` for their section by
		overriding clean_values. Not bound to a model -- follows the guru
		GuruCoreDataForm convention for nested data validation (AR-3).
	'''
	version = forms.RegexField(regex=PREF_VERSION_REGEX)
	# Optional so that an empty section object (`{}`) is accepted: forms.JSONField
	# treats `{}`/`[]` as empty values and would otherwise reject them as required.
	values = forms.JSONField(required=False)

	def clean_values(self):
		values = self.cleaned_data.get('values')
		if values is None:
			# Absent or empty (`{}`) `values` normalizes to an empty section.
			return {}
		if not isinstance(values, dict):
			raise forms.ValidationError('`values` must be an object.')
		return values


class GeneralPrefForm(UserPrefSectionForm):
	'''	General preferences:
		`{ language?: string, offlineArchiveTransfer?: bool, offlineRetryAttempts?: int }`.

		The key set is closed: an unrecognised key is a validation error.
	'''
	# Per-image attempt budget for offline transfers (ohif-viewers#131 FR-12). Bounded here as
	# well as in the viewer: the viewer clamps for the user's benefit, this rejects for the
	# document's -- a stored value outside the range would be applied by no client and read as
	# a setting by every one of them.
	OFFLINE_RETRY_ATTEMPTS_MIN = 1
	OFFLINE_RETRY_ATTEMPTS_MAX = 5

	def clean_values(self):
		values = super().clean_values()

		unknown = set(values) - {'language', 'offlineArchiveTransfer', 'offlineRetryAttempts'}
		if unknown:
			raise forms.ValidationError('Unknown keys: %s' % ', '.join(sorted(unknown)))

		if 'language' in values and not isinstance(values['language'], str):
			raise forms.ValidationError('`language` must be a string.')

		if 'offlineArchiveTransfer' in values and not isinstance(values['offlineArchiveTransfer'], bool):
			raise forms.ValidationError('`offlineArchiveTransfer` must be a boolean.')

		if 'offlineRetryAttempts' in values:
			attempts = values['offlineRetryAttempts']

			# `bool` is a subclass of `int`, and `True` is not an attempt count.
			if isinstance(attempts, bool) or not isinstance(attempts, int):
				raise forms.ValidationError('`offlineRetryAttempts` must be an integer.')
			if not self.OFFLINE_RETRY_ATTEMPTS_MIN <= attempts <= self.OFFLINE_RETRY_ATTEMPTS_MAX:
				raise forms.ValidationError('`offlineRetryAttempts` must be between %d and %d.'
					% (self.OFFLINE_RETRY_ATTEMPTS_MIN, self.OFFLINE_RETRY_ATTEMPTS_MAX))

		return values


class HotkeysPrefForm(UserPrefSectionForm):
	'''	Hotkeys: map of `commandName -> { label: string, keys: string[] }`.
	'''
	def clean_values(self):
		values = super().clean_values()

		for command, definition in values.items():
			if not isinstance(definition, dict):
				raise forms.ValidationError('Hotkey %r must be an object.' % command)
			if not isinstance(definition.get('label'), str):
				raise forms.ValidationError('Hotkey %r `label` must be a string.' % command)

			keys = definition.get('keys')
			if not isinstance(keys, list) or not all(isinstance(key, str) for key in keys):
				raise forms.ValidationError('Hotkey %r `keys` must be a list of strings.' % command)

		return values


class WindowLevelPrefForm(UserPrefSectionForm):
	'''	Window-level presets: map of `"1".."10" -> { description, window, level }`
		(all string values).
	'''
	def clean_values(self):
		values = super().clean_values()

		for preset, definition in values.items():
			if preset not in WINDOW_LEVEL_PRESET_KEYS:
				raise forms.ValidationError('Invalid window-level preset key: %r' % preset)
			if not isinstance(definition, dict):
				raise forms.ValidationError('Window-level preset %r must be an object.' % preset)
			for field in ('description', 'window', 'level'):
				if not isinstance(definition.get(field), str):
					raise forms.ValidationError(
						'Window-level preset %r field %r must be a string.' % (preset, field))

		return values


class ViewerMetaPrefForm(UserPrefSectionForm):
	'''	Viewer-metadata four-corner overlay: `{ <corner>: [ { title, value } ] }`,
		each corner an array of at most LIMIT_CORNER_ITEMS entries.
	'''
	def clean_values(self):
		values = super().clean_values()

		unknown = set(values) - set(VIEWER_META_CORNERS)
		if unknown:
			raise forms.ValidationError('Unknown corner keys: %s' % ', '.join(sorted(unknown)))

		for corner, items in values.items():
			if not isinstance(items, list):
				raise forms.ValidationError('Corner %r must be a list.' % corner)
			if len(items) > VIEWER_META_CORNER_LIMIT:
				raise forms.ValidationError(
					'Corner %r exceeds the %d item limit.' % (corner, VIEWER_META_CORNER_LIMIT))
			for item in items:
				if not isinstance(item, dict) \
						or not isinstance(item.get('title'), str) \
						or not isinstance(item.get('value'), str):
					raise forms.ValidationError(
						'Corner %r items must be objects with string `title` and `value`.' % corner)

		return values


class StudylistPrefForm(UserPrefSectionForm):
	'''	Study-list display configuration (FR-15): `values` is a map whose keys are a
		subset of {worklist, allStudies, shared, upload}. `worklist`/`allStudies`/`shared`
		carry `selectedFilters`, `selectedColumns`, `columnOrder`; `upload` carries
		`selectedColumns`, `columnOrder` only (no `selectedFilters`). Every field is an
		array of non-empty strings within sane bounds.
	'''
	def clean_values(self):
		values = super().clean_values()

		if not values:
			raise forms.ValidationError('At least one interface must be provided.')

		unknown = set(values) - set(STUDYLIST_INTERFACES)
		if unknown:
			raise forms.ValidationError('Unknown interface keys: %s' % ', '.join(sorted(unknown)))

		for interface, subdocument in values.items():
			if not isinstance(subdocument, dict):
				raise forms.ValidationError('Interface %r must be an object.' % interface)

			allowed_fields = {'selectedColumns', 'columnOrder'}
			if interface != 'upload':
				allowed_fields.add('selectedFilters')

			invalid_fields = set(subdocument) - allowed_fields
			if invalid_fields:
				# `selectedFilters` on `upload` lands here as well (FR-15).
				raise forms.ValidationError(
					'Interface %r has invalid fields: %s' % (interface, ', '.join(sorted(invalid_fields))))

			for field, entries in subdocument.items():
				self._validate_string_array(interface, field, entries)

		return values

	def _validate_string_array(self, interface, field, entries):
		'''	Validate that `entries` is an array of non-empty strings within bounds.
		'''
		if not isinstance(entries, list):
			raise forms.ValidationError('%s.%s must be a list.' % (interface, field))
		if len(entries) > STUDYLIST_MAX_ENTRIES:
			raise forms.ValidationError(
				'%s.%s exceeds the %d entry limit.' % (interface, field, STUDYLIST_MAX_ENTRIES))
		for entry in entries:
			if not isinstance(entry, str) or not entry:
				raise forms.ValidationError('%s.%s entries must be non-empty strings.' % (interface, field))
			if len(entry) > STUDYLIST_MAX_STRING:
				raise forms.ValidationError(
					'%s.%s entries must be at most %d characters.' % (interface, field, STUDYLIST_MAX_STRING))
