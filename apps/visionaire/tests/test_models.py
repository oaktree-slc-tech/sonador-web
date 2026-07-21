'''	Unit tests for the UserPref model section helpers and the FR-12 legacy-nesting
	transform (Backend unit-test plan §3 and §4). These exercise pure in-memory logic and
	do not touch the database.
'''
from django.test import SimpleTestCase

from ..models.userpref import UserPref, CURRENT_PREF_VERSION, LEGACY_PREF_VERSION
from . import fixtures


class SectionHelperTests(SimpleTestCase):
	'''	get_section / set_section / merge_interfaces (§3).
	'''

	def test_get_section_from_empty_field_returns_empty(self):
		userpref = UserPref()
		self.assertEqual(userpref.get_section('viewer', CURRENT_PREF_VERSION, 'general'), {})
		# Whole-version read (studylist GET path) on an empty field.
		self.assertEqual(userpref.get_section('studylist', CURRENT_PREF_VERSION), {})

	def test_get_section_missing_version_or_section_returns_empty(self):
		userpref = UserPref(viewer={CURRENT_PREF_VERSION: {'general': {'language': 'en-US'}}})
		self.assertEqual(userpref.get_section('viewer', '9.9', 'general'), {})
		self.assertEqual(userpref.get_section('viewer', CURRENT_PREF_VERSION, 'hotkeys'), {})

	def test_set_section_creates_nested_structure_from_none(self):
		userpref = UserPref()
		returned = userpref.set_section('viewer', CURRENT_PREF_VERSION, 'general', fixtures.DEFAULT_GENERAL)
		self.assertEqual(returned, fixtures.DEFAULT_GENERAL)
		self.assertEqual(userpref.viewer, {CURRENT_PREF_VERSION: {'general': fixtures.DEFAULT_GENERAL}})

	def test_set_section_leaves_other_sections_and_versions_intact(self):
		userpref = UserPref(viewer={
			CURRENT_PREF_VERSION: {'hotkeys': dict(fixtures.DEFAULT_HOTKEYS)},
			LEGACY_PREF_VERSION: {'general': {'language': 'fr-FR'}},
		})
		userpref.set_section('viewer', CURRENT_PREF_VERSION, 'general', fixtures.DEFAULT_GENERAL)
		self.assertEqual(userpref.viewer[CURRENT_PREF_VERSION]['general'], fixtures.DEFAULT_GENERAL)
		# Sibling section unchanged.
		self.assertEqual(userpref.viewer[CURRENT_PREF_VERSION]['hotkeys'], fixtures.DEFAULT_HOTKEYS)
		# Other version unchanged.
		self.assertEqual(userpref.viewer[LEGACY_PREF_VERSION], {'general': {'language': 'fr-FR'}})

	def test_merge_interfaces_replaces_only_provided_interfaces(self):
		userpref = UserPref(studylist={
			CURRENT_PREF_VERSION: {
				'allStudies': dict(fixtures.DEFAULT_STUDYLIST['allStudies']),
				'shared': dict(fixtures.DEFAULT_STUDYLIST['shared']),
			}
		})
		worklist_slice = dict(fixtures.DEFAULT_STUDYLIST['worklist'])
		returned = userpref.merge_interfaces(CURRENT_PREF_VERSION, {'worklist': worklist_slice})

		# worklist added; allStudies / shared untouched.
		self.assertEqual(userpref.studylist[CURRENT_PREF_VERSION]['worklist'], worklist_slice)
		self.assertEqual(userpref.studylist[CURRENT_PREF_VERSION]['allStudies'],
			fixtures.DEFAULT_STUDYLIST['allStudies'])
		self.assertEqual(userpref.studylist[CURRENT_PREF_VERSION]['shared'],
			fixtures.DEFAULT_STUDYLIST['shared'])
		# Returned value is the full version document after merge.
		self.assertEqual(set(returned), {'worklist', 'allStudies', 'shared'})

	def test_set_section_does_not_alias_existing_document(self):
		'''	Mutating helpers must not mutate the previously-stored nested dicts in place
			(so concurrent readers / byte-for-byte assertions hold).
		'''
		original_version_doc = {'hotkeys': dict(fixtures.DEFAULT_HOTKEYS)}
		userpref = UserPref(viewer={CURRENT_PREF_VERSION: original_version_doc})
		userpref.set_section('viewer', CURRENT_PREF_VERSION, 'general', fixtures.DEFAULT_GENERAL)
		self.assertNotIn('general', original_version_doc)

	def test_invalid_field_rejected(self):
		with self.assertRaises(ValueError):
			UserPref().get_section('not_a_field', CURRENT_PREF_VERSION, 'general')


class NestLegacyDocumentTests(SimpleTestCase):
	'''	FR-12 transform (§4).
	'''

	def test_flat_document_is_nested_under_legacy_version(self):
		flat = {'general': {'language': 'en-US'}, 'hotkeys': dict(fixtures.DEFAULT_HOTKEYS)}
		self.assertEqual(
			UserPref.nest_legacy_document(flat),
			{LEGACY_PREF_VERSION: flat})

	def test_flat_studylist_document_is_nested(self):
		flat = {'worklist': dict(fixtures.DEFAULT_STUDYLIST['worklist'])}
		self.assertEqual(
			UserPref.nest_legacy_document(flat),
			{LEGACY_PREF_VERSION: flat})

	def test_already_versioned_document_is_unchanged(self):
		versioned = fixtures.viewer_document()
		self.assertIs(UserPref.nest_legacy_document(versioned), versioned)

	def test_null_and_empty_documents_are_unchanged(self):
		self.assertIsNone(UserPref.nest_legacy_document(None))
		self.assertEqual(UserPref.nest_legacy_document({}), {})

	def test_transform_is_idempotent(self):
		flat = {'general': {'language': 'en-US'}}
		once = UserPref.nest_legacy_document(flat)
		twice = UserPref.nest_legacy_document(once)
		self.assertEqual(twice, once)
		self.assertEqual(twice, {LEGACY_PREF_VERSION: flat})

	def test_multi_version_document_is_treated_as_versioned(self):
		document = {'0.3': {'general': {}}, '0.4': {'general': {'language': 'en-US'}}}
		self.assertIs(UserPref.nest_legacy_document(document), document)
