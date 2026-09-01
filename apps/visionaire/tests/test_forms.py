'''	Unit tests for the section forms (Backend unit-test plan §1). Fixtures are the real
	0.4 default shapes from `fixtures` (§5.1).
'''
from django.test import SimpleTestCase, TestCase

from ..forms.userpref import (
	UserPrefForm, GeneralPrefForm, HotkeysPrefForm,
	WindowLevelPrefForm, ViewerMetaPrefForm, StudylistPrefForm,
)
from . import fixtures


def section_data(values, version='0.4'):
	return {'version': version, 'values': values}


class SectionVersionTests(SimpleTestCase):
	'''	UserPrefSectionForm base: version + values envelope validation.
	'''

	def test_accepts_valid_versions(self):
		for version in ('0.3', '0.4', '10.12'):
			form = GeneralPrefForm(section_data({}, version=version))
			self.assertTrue(form.is_valid(), '%s: %s' % (version, form.errors.as_json()))

	def test_rejects_malformed_versions(self):
		for version in ('0.4.1', 'v0.4', '0.4-beta', ''):
			form = GeneralPrefForm(section_data({}, version=version))
			self.assertFalse(form.is_valid(), 'expected %r to be rejected' % version)
			self.assertIn('version', form.errors)

	def test_rejects_missing_version(self):
		form = GeneralPrefForm({'values': {}})
		self.assertFalse(form.is_valid())
		self.assertIn('version', form.errors)

	def test_rejects_non_object_values(self):
		form = GeneralPrefForm(section_data(['not', 'an', 'object']))
		self.assertFalse(form.is_valid())
		self.assertIn('values', form.errors)


class GeneralPrefFormTests(SimpleTestCase):

	def test_accepts_empty_and_language(self):
		self.assertTrue(GeneralPrefForm(section_data({})).is_valid())
		self.assertTrue(GeneralPrefForm(section_data(fixtures.DEFAULT_GENERAL)).is_valid())

	def test_rejects_non_string_language(self):
		form = GeneralPrefForm(section_data({'language': 5}))
		self.assertFalse(form.is_valid())
		self.assertIn('values', form.errors)

	def test_rejects_unknown_keys(self):
		form = GeneralPrefForm(section_data({'language': 'en-US', 'theme': 'dark'}))
		self.assertFalse(form.is_valid())
		self.assertIn('values', form.errors)

	def test_accepts_offline_archive_transfer_boolean(self):
		for value in (True, False):
			form = GeneralPrefForm(section_data({'offlineArchiveTransfer': value}))
			self.assertTrue(form.is_valid(), form.errors.as_json())
			self.assertEqual(form.cleaned_data['values'], {'offlineArchiveTransfer': value})

	def test_accepts_offline_archive_transfer_alongside_language(self):
		values = {'language': 'en-US', 'offlineArchiveTransfer': True}
		form = GeneralPrefForm(section_data(values))
		self.assertTrue(form.is_valid(), form.errors.as_json())
		self.assertEqual(form.cleaned_data['values'], values)

	def test_rejects_non_boolean_offline_archive_transfer(self):
		# Including the JSON-ish values a client might send for a checkbox. `1` matters: in Python
		# it is an int, but `isinstance(1, bool)` is False, so a bare truthiness check would let it
		# through and store a non-boolean in the preference document.
		for value in ('true', 1, 0, None, [], {}):
			form = GeneralPrefForm(section_data({'offlineArchiveTransfer': value}))
			self.assertFalse(form.is_valid(), 'accepted %r' % (value,))
			self.assertIn('values', form.errors)

	def test_accepts_offline_retry_attempts_in_range(self):
		for value in (1, 3, 5):
			form = GeneralPrefForm(section_data({'offlineRetryAttempts': value}))
			self.assertTrue(form.is_valid(), form.errors.as_json())
			self.assertEqual(form.cleaned_data['values'], {'offlineRetryAttempts': value})

	def test_accepts_offline_retry_attempts_alongside_the_other_general_keys(self):
		# The viewer POSTs the section wholesale, so the three keys have to validate together.
		values = {'language': 'en-US', 'offlineArchiveTransfer': True, 'offlineRetryAttempts': 4}
		form = GeneralPrefForm(section_data(values))
		self.assertTrue(form.is_valid(), form.errors.as_json())
		self.assertEqual(form.cleaned_data['values'], values)

	def test_rejects_out_of_range_or_non_integer_offline_retry_attempts(self):
		# `True` is in the list deliberately: bool is a subclass of int, so an isinstance check on
		# its own would store `True` as an attempt count.
		for value in (0, 6, -1, '3', 3.5, True, None, [], {}):
			form = GeneralPrefForm(section_data({'offlineRetryAttempts': value}))
			self.assertFalse(form.is_valid(), 'accepted %r' % (value,))
			self.assertIn('values', form.errors)


class HotkeysPrefFormTests(SimpleTestCase):

	def test_accepts_full_default_hotkey_set(self):
		form = HotkeysPrefForm(section_data(fixtures.DEFAULT_HOTKEYS))
		self.assertTrue(form.is_valid(), form.errors.as_json())

	def test_rejects_keys_as_string(self):
		form = HotkeysPrefForm(section_data({'setZoomTool': {'label': 'Zoom', 'keys': 'z'}}))
		self.assertFalse(form.is_valid())

	def test_rejects_non_string_key_entries(self):
		form = HotkeysPrefForm(section_data({'setZoomTool': {'label': 'Zoom', 'keys': [1]}}))
		self.assertFalse(form.is_valid())

	def test_rejects_non_object_command_value(self):
		form = HotkeysPrefForm(section_data({'setZoomTool': 'z'}))
		self.assertFalse(form.is_valid())


class WindowLevelPrefFormTests(SimpleTestCase):

	def test_accepts_ten_default_presets(self):
		form = WindowLevelPrefForm(section_data(fixtures.DEFAULT_WINDOW_LEVEL))
		self.assertTrue(form.is_valid(), form.errors.as_json())

	def test_rejects_out_of_range_preset_keys(self):
		for key in ('0', '11'):
			form = WindowLevelPrefForm(section_data({key: {'description': 'x', 'window': '1', 'level': '1'}}))
			self.assertFalse(form.is_valid(), 'expected preset key %r rejected' % key)

	def test_rejects_missing_fields(self):
		form = WindowLevelPrefForm(section_data({'1': {'description': 'Soft tissue', 'window': '550'}}))
		self.assertFalse(form.is_valid())

	def test_rejects_non_object_preset(self):
		form = WindowLevelPrefForm(section_data({'1': 'soft'}))
		self.assertFalse(form.is_valid())


class ViewerMetaPrefFormTests(SimpleTestCase):

	def test_accepts_four_corner_defaults(self):
		form = ViewerMetaPrefForm(section_data(fixtures.DEFAULT_VIEWER_METADATA))
		self.assertTrue(form.is_valid(), form.errors.as_json())

	def test_rejects_eleventh_corner_item(self):
		too_many = [{'title': 't%d' % i, 'value': 'v%d' % i} for i in range(11)]
		form = ViewerMetaPrefForm(section_data({'topLeftCorner': too_many}))
		self.assertFalse(form.is_valid())

	def test_rejects_unknown_corner_key(self):
		form = ViewerMetaPrefForm(section_data({'centerCorner': []}))
		self.assertFalse(form.is_valid())

	def test_rejects_item_missing_value(self):
		form = ViewerMetaPrefForm(section_data({'topLeftCorner': [{'title': 'Patient Name'}]}))
		self.assertFalse(form.is_valid())


class StudylistPrefFormTests(SimpleTestCase):

	def test_accepts_single_interface_payload(self):
		form = StudylistPrefForm(section_data({'worklist': fixtures.DEFAULT_STUDYLIST['worklist']}))
		self.assertTrue(form.is_valid(), form.errors.as_json())

	def test_accepts_full_four_interface_payload(self):
		form = StudylistPrefForm(section_data(fixtures.DEFAULT_STUDYLIST))
		self.assertTrue(form.is_valid(), form.errors.as_json())

	def test_rejects_unknown_interface_key(self):
		form = StudylistPrefForm(section_data({'bogus': {'selectedColumns': ['PatientName']}}))
		self.assertFalse(form.is_valid())

	def test_rejects_selected_filters_on_upload(self):
		form = StudylistPrefForm(section_data({
			'upload': {'selectedFilters': ['PatientID'], 'selectedColumns': ['PatientName']},
		}))
		self.assertFalse(form.is_valid())

	def test_rejects_non_array_field(self):
		form = StudylistPrefForm(section_data({'worklist': {'selectedColumns': 'PatientName'}}))
		self.assertFalse(form.is_valid())

	def test_rejects_non_string_array_entries(self):
		form = StudylistPrefForm(section_data({'worklist': {'selectedColumns': [1, 2]}}))
		self.assertFalse(form.is_valid())

	def test_rejects_empty_string_entries(self):
		form = StudylistPrefForm(section_data({'worklist': {'selectedColumns': ['']}}))
		self.assertFalse(form.is_valid())

	def test_rejects_too_many_entries(self):
		form = StudylistPrefForm(section_data({'worklist': {'selectedColumns': ['c%d' % i for i in range(65)]}}))
		self.assertFalse(form.is_valid())

	def test_rejects_overlong_string(self):
		form = StudylistPrefForm(section_data({'worklist': {'selectedColumns': ['x' * 129]}}))
		self.assertFalse(form.is_valid())


class UserPrefFormTests(TestCase):
	'''	Reworked whole-document form (AR-6 / FR-5).
	'''

	def test_viewer_and_studylist_are_optional(self):
		self.assertTrue(UserPrefForm({}).is_valid())
		self.assertTrue(UserPrefForm({'viewer': fixtures.viewer_document()}).is_valid())

	def test_user_field_not_accepted_from_form_data(self):
		self.assertNotIn('user', UserPrefForm({}).fields)
