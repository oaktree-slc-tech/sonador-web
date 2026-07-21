'''	Unit tests for the FR-12 data migration (Backend unit-test plan §4). Exercises the
	migration's row-level RunPython function against seeded rows, including idempotency.
	(The pure transform is additionally covered in test_models.NestLegacyDocumentTests.)
'''
import importlib

from django.apps import apps as global_apps
from django.contrib.auth.models import User
from django.test import TestCase

from ..models.userpref import UserPref
from . import fixtures

# The migration module name begins with a digit, so import it by string.
_migration = importlib.import_module('visionaire.migrations.0001_nest_legacy_preferences')
nest_legacy_preferences = _migration.nest_legacy_preferences


class Fr12MigrationTests(TestCase):

	def _run(self):
		nest_legacy_preferences(global_apps, None)

	def test_flat_viewer_and_studylist_are_nested_under_0_3(self):
		flat_viewer = {'general': {'language': 'en-US'}, 'hotkeys': dict(fixtures.DEFAULT_HOTKEYS)}
		flat_studylist = {'worklist': dict(fixtures.DEFAULT_STUDYLIST['worklist'])}
		user = User.objects.create_user('legacy.user', password='x')
		UserPref.objects.create(user=user, viewer=dict(flat_viewer), studylist=dict(flat_studylist))

		self._run()

		row = UserPref.objects.get(user=user)
		self.assertEqual(row.viewer, {'0.3': flat_viewer})
		self.assertEqual(row.studylist, {'0.3': flat_studylist})

	def test_already_versioned_documents_untouched(self):
		viewer = fixtures.viewer_document()
		studylist = fixtures.studylist_document()
		user = User.objects.create_user('versioned.user', password='x')
		UserPref.objects.create(user=user, viewer=viewer, studylist=studylist)

		self._run()

		row = UserPref.objects.get(user=user)
		self.assertEqual(row.viewer, viewer)
		self.assertEqual(row.studylist, studylist)

	def test_null_and_empty_fields_untouched(self):
		null_user = User.objects.create_user('null.user', password='x')
		UserPref.objects.create(user=null_user, viewer=None, studylist=None)
		empty_user = User.objects.create_user('empty.user', password='x')
		UserPref.objects.create(user=empty_user, viewer={}, studylist={})

		self._run()

		null_row = UserPref.objects.get(user=null_user)
		self.assertIsNone(null_row.viewer)
		self.assertIsNone(null_row.studylist)
		empty_row = UserPref.objects.get(user=empty_user)
		self.assertEqual(empty_row.viewer, {})
		self.assertEqual(empty_row.studylist, {})

	def test_migration_is_idempotent(self):
		flat_viewer = {'general': {'language': 'en-US'}}
		user = User.objects.create_user('idem.user', password='x')
		UserPref.objects.create(user=user, viewer=dict(flat_viewer), studylist=None)

		self._run()
		self._run()   # second pass must be a no-op

		row = UserPref.objects.get(user=user)
		self.assertEqual(row.viewer, {'0.3': flat_viewer})
		self.assertIsNone(row.studylist)
