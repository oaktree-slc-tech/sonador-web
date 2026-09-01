'''	Unit tests for UserPrefSectionApiView behavior (Backend unit-test plan §2). The view
	is exercised directly via RequestFactory with an authenticated user; the `api_request`
	bearer-token wrapper (401s / OPTIONS) is applied at the URL layer and covered by the
	functional suite, so it is bypassed here.
'''
import json
from unittest import mock

from django.contrib.auth.models import User
from django.test import RequestFactory, TransactionTestCase

from ..models.userpref import UserPref
from ..forms.userpref import (
	GeneralPrefForm, HotkeysPrefForm, WindowLevelPrefForm, ViewerMetaPrefForm, StudylistPrefForm,
)
from ..views.userpref import UserPrefSectionApiView
from . import fixtures


GENERAL = UserPrefSectionApiView.as_view(section='general', formclass=GeneralPrefForm, field='viewer')
HOTKEYS = UserPrefSectionApiView.as_view(section='hotkeys', formclass=HotkeysPrefForm, field='viewer')
WINDOW_LEVEL = UserPrefSectionApiView.as_view(section='windowLevel', formclass=WindowLevelPrefForm, field='viewer')
VIEWER_META = UserPrefSectionApiView.as_view(section='viewerMetadata', formclass=ViewerMetaPrefForm, field='viewer')
STUDYLIST = UserPrefSectionApiView.as_view(section=None, formclass=StudylistPrefForm, field='studylist')

PATH = '/visionaire/api/user-preferences/section/'


class SectionViewTestCase(TransactionTestCase):
	'''	Shared setup + request helpers.
	'''
	def setUp(self):
		self.factory = RequestFactory()
		self.user = User.objects.create_user('victor.orlyk', password='x')

	def _dispatch(self, view, request):
		request.user = self.user
		return view(request)

	def get(self, view, version=None):
		query = ('?version=%s' % version) if version else ''
		return self._dispatch(view, self.factory.get(PATH + query))

	def post(self, view, version, values):
		request = self.factory.post(
			PATH, data=json.dumps({'version': version, 'values': values}),
			content_type='application/json')
		return self._dispatch(view, request)

	def results(self, response):
		return json.loads(response.content)['results']


class SectionGetTests(SectionViewTestCase):

	def test_get_on_empty_account_returns_empty_and_creates_row(self):
		self.assertFalse(UserPref.objects.filter(user=self.user).exists())
		response = self.get(GENERAL)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(self.results(response), {'version': '0.4', 'values': {}})
		# get_or_create side effect.
		self.assertTrue(UserPref.objects.filter(user=self.user).exists())

	def test_get_respects_version_query_param(self):
		UserPref.objects.create(user=self.user, viewer={
			'0.3': {'general': {'language': 'fr-FR'}},
			'0.4': {'general': {'language': 'en-US'}},
		})
		self.assertEqual(self.results(self.get(GENERAL, version='0.3')),
			{'version': '0.3', 'values': {'language': 'fr-FR'}})
		self.assertEqual(self.results(self.get(GENERAL, version='0.4')),
			{'version': '0.4', 'values': {'language': 'en-US'}})


class SectionPostTests(SectionViewTestCase):

	def test_post_persists_section_and_returns_stored_values(self):
		response = self.post(HOTKEYS, '0.4', fixtures.DEFAULT_HOTKEYS)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(self.results(response), {'version': '0.4', 'values': fixtures.DEFAULT_HOTKEYS})

		row = UserPref.objects.get(user=self.user)
		self.assertEqual(row.viewer['0.4']['hotkeys'], fixtures.DEFAULT_HOTKEYS)

	def test_post_leaves_other_sections_and_versions_byte_for_byte(self):
		seed = {
			'0.3': {'general': {'language': 'fr-FR'}},
			'0.4': {
				'hotkeys': dict(fixtures.DEFAULT_HOTKEYS),
				'windowLevel': dict(fixtures.DEFAULT_WINDOW_LEVEL),
			},
		}
		UserPref.objects.create(user=self.user, viewer=json.loads(json.dumps(seed)))

		self.post(GENERAL, '0.4', fixtures.DEFAULT_GENERAL)

		row = UserPref.objects.get(user=self.user)
		self.assertEqual(row.viewer['0.4']['general'], fixtures.DEFAULT_GENERAL)
		self.assertEqual(row.viewer['0.4']['hotkeys'], seed['0.4']['hotkeys'])
		self.assertEqual(row.viewer['0.4']['windowLevel'], seed['0.4']['windowLevel'])
		self.assertEqual(row.viewer['0.3'], seed['0.3'])

	def test_invalid_payload_returns_400_and_writes_nothing(self):
		UserPref.objects.create(user=self.user, viewer={'0.4': {'general': {'language': 'en-US'}}})
		response = self.post(GENERAL, '0.4', {'language': 5})   # non-string language
		self.assertEqual(response.status_code, 400)
		self.assertIn('errors', json.loads(response.content))
		# Row unchanged.
		row = UserPref.objects.get(user=self.user)
		self.assertEqual(row.viewer, {'0.4': {'general': {'language': 'en-US'}}})

	def test_offline_archive_transfer_round_trips_through_the_section_endpoint(self):
		# The frontend/backend contract this key exists for: both values accepted, persisted, and
		# handed back by a subsequent GET (ohif-viewers#129 FR-1).
		for value in (True, False):
			values = {'language': 'en-US', 'offlineArchiveTransfer': value}
			response = self.post(GENERAL, '0.4', values)
			self.assertEqual(response.status_code, 200)
			self.assertEqual(self.results(response), {'version': '0.4', 'values': values})

			row = UserPref.objects.get(user=self.user)
			self.assertEqual(row.viewer['0.4']['general'], values)
			self.assertIs(row.viewer['0.4']['general']['offlineArchiveTransfer'], value)

			self.assertEqual(self.results(self.get(GENERAL, version='0.4')),
				{'version': '0.4', 'values': values})

	def test_non_boolean_offline_archive_transfer_returns_400_and_writes_nothing(self):
		stored = {'language': 'en-US', 'offlineArchiveTransfer': True}
		UserPref.objects.create(user=self.user, viewer={'0.4': {'general': dict(stored)}})

		response = self.post(GENERAL, '0.4', {'offlineArchiveTransfer': 'true'})

		self.assertEqual(response.status_code, 400)
		self.assertIn('errors', json.loads(response.content))
		row = UserPref.objects.get(user=self.user)
		self.assertEqual(row.viewer, {'0.4': {'general': stored}})

	def test_offline_retry_attempts_round_trips_through_the_section_endpoint(self):
		# ohif-viewers#131 FR-12: the viewer POSTs the general section wholesale, so the attempt
		# budget has to persist alongside the keys that were already there.
		values = {'language': 'en-US', 'offlineArchiveTransfer': True, 'offlineRetryAttempts': 5}
		response = self.post(GENERAL, '0.4', values)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(self.results(response), {'version': '0.4', 'values': values})
		self.assertEqual(UserPref.objects.get(user=self.user).viewer['0.4']['general'], values)
		self.assertEqual(self.results(self.get(GENERAL, version='0.4')),
			{'version': '0.4', 'values': values})

	def test_out_of_range_offline_retry_attempts_returns_400_and_writes_nothing(self):
		stored = {'language': 'en-US', 'offlineRetryAttempts': 3}
		UserPref.objects.create(user=self.user, viewer={'0.4': {'general': dict(stored)}})

		response = self.post(GENERAL, '0.4', {'offlineRetryAttempts': 9})

		self.assertEqual(response.status_code, 400)
		self.assertIn('errors', json.loads(response.content))
		row = UserPref.objects.get(user=self.user)
		self.assertEqual(row.viewer, {'0.4': {'general': stored}})

	def test_unknown_general_key_still_rejected_alongside_the_new_one(self):
		# The allowlist widened by exactly two keys; anything else must still be refused.
		response = self.post(GENERAL, '0.4', {'offlineArchiveTransfer': True, 'theme': 'dark'})

		self.assertEqual(response.status_code, 400)
		# A rejected POST writes nothing at all -- not even the get_or_create row a GET would make.
		self.assertFalse(UserPref.objects.filter(user=self.user).exists())

	def test_field_routing_viewer_vs_studylist(self):
		self.post(GENERAL, '0.4', fixtures.DEFAULT_GENERAL)
		row = UserPref.objects.get(user=self.user)
		self.assertIn('general', row.viewer['0.4'])
		self.assertIsNone(row.studylist)

		self.post(STUDYLIST, '0.4', {'worklist': fixtures.DEFAULT_STUDYLIST['worklist']})
		row.refresh_from_db()
		self.assertIn('worklist', row.studylist['0.4'])
		# Viewer field never touched by the studylist write.
		self.assertEqual(row.viewer, {'0.4': {'general': fixtures.DEFAULT_GENERAL}})


class StudylistMergeTests(SectionViewTestCase):

	def test_interface_level_merge_leaves_absent_interfaces_untouched(self):
		UserPref.objects.create(user=self.user, studylist={'0.4': {
			'allStudies': dict(fixtures.DEFAULT_STUDYLIST['allStudies']),
			'shared': dict(fixtures.DEFAULT_STUDYLIST['shared']),
		}})

		response = self.post(STUDYLIST, '0.4', {'worklist': fixtures.DEFAULT_STUDYLIST['worklist']})
		self.assertEqual(response.status_code, 200)

		row = UserPref.objects.get(user=self.user)
		self.assertEqual(row.studylist['0.4']['worklist'], fixtures.DEFAULT_STUDYLIST['worklist'])
		self.assertEqual(row.studylist['0.4']['allStudies'], fixtures.DEFAULT_STUDYLIST['allStudies'])
		self.assertEqual(row.studylist['0.4']['shared'], fixtures.DEFAULT_STUDYLIST['shared'])

		# GET returns all three interfaces for the version.
		values = self.results(self.get(STUDYLIST, version='0.4'))['values']
		self.assertEqual(set(values), {'worklist', 'allStudies', 'shared'})


class ConcurrencyTests(SectionViewTestCase):
	'''	FR-6: writes run inside transaction.atomic() with the row locked.
	'''

	def test_two_sequential_section_writes_both_persist(self):
		self.post(HOTKEYS, '0.4', fixtures.DEFAULT_HOTKEYS)
		self.post(WINDOW_LEVEL, '0.4', fixtures.DEFAULT_WINDOW_LEVEL)

		row = UserPref.objects.get(user=self.user)
		self.assertEqual(row.viewer['0.4']['hotkeys'], fixtures.DEFAULT_HOTKEYS)
		self.assertEqual(row.viewer['0.4']['windowLevel'], fixtures.DEFAULT_WINDOW_LEVEL)

	def test_post_path_locks_row_with_select_for_update(self):
		with mock.patch.object(
				UserPref.objects, 'select_for_update',
				wraps=UserPref.objects.select_for_update) as spy:
			response = self.post(GENERAL, '0.4', fixtures.DEFAULT_GENERAL)
		self.assertEqual(response.status_code, 200)
		self.assertTrue(spy.called, 'expected the POST path to lock the row via select_for_update')
