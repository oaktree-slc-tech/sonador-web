"""	Comment DELETE authorization in the shared resource permission resolver.

	A comment removal is admitted by `comment_edit` (own comments, ownership enforced by the Orthanc
	comment endpoint) or by `remove` on the resource. Adding and editing stay on `comment_edit`;
	imaging-resource removal stays on `remove`.
"""
from unittest import mock

from django.test import SimpleTestCase, TestCase

from orthancapi import apisettings as orthanc_api
from orthancapi.auth.acl import ResourceAuthorization


SERIES_ID = '437ce199-d7e4b001-5e779d3f-2077c411-5beab5cd'
COMMENT_URI = '/series/%s/comments/7fd9db40-cd0c-4266-853e-a69cbbbce57d' % SERIES_ID
DICOMWEB_COMMENT_URI = '/dicom-web/series/1.2.3/comments/7fd9db40-cd0c-4266-853e-a69cbbbce57d'
SERIES = orthanc_api.ORTHANC_RESOURCE_SERIES


def perm(**grants):
	return ResourceAuthorization(**grants)


class CommentRemovalPermissionTests(SimpleTestCase):

	def _delete(self, auth, resource=COMMENT_URI, action=orthanc_api.ORTHANC_ACTION_COMMENT, level=SERIES):
		return auth.resource_perm(resource, SERIES_ID, 'DELETE', level, action=action)

	def test_comment_edit_admits_comment_delete(self):
		self.assertTrue(self._delete(perm(view=True, comment_edit=True, remove=False)))

	def test_remove_admits_comment_delete_without_comment_edit(self):
		self.assertTrue(self._delete(perm(view=True, comment_edit=False, remove=True)))

	def test_neither_grant_refuses_comment_delete(self):
		self.assertFalse(self._delete(perm(view=True, modify=True, comment_edit=False, remove=False)))

	def test_no_decision_when_neither_permission_is_set(self):
		# A local policy that says nothing about either permission defers to the global policy.
		self.assertIsNone(self._delete(perm(view=True)))

	def test_dicomweb_comment_delete_follows_the_same_rule(self):
		# The DICOMweb item route arrives with no action token; the generic DELETE branch handles it.
		self.assertTrue(self._delete(perm(comment_edit=False, remove=True), resource=DICOMWEB_COMMENT_URI, action=None))
		self.assertTrue(self._delete(perm(comment_edit=True, remove=False), resource=DICOMWEB_COMMENT_URI, action=None))
		self.assertFalse(self._delete(perm(comment_edit=False, remove=False), resource=DICOMWEB_COMMENT_URI, action=None))

	def test_system_level_comment_delete_follows_the_same_rule(self):
		self.assertTrue(self._delete(perm(comment_edit=False, remove=True), level=orthanc_api.ORTHANC_SYSTEM, action=None))
		self.assertFalse(self._delete(perm(comment_edit=False, remove=False), level=orthanc_api.ORTHANC_SYSTEM, action=None))

	def test_add_and_edit_stay_on_comment_edit(self):
		auth = perm(view=True, comment_edit=False, remove=True, modify=True)

		for method in ('POST', 'PUT'):
			self.assertFalse(auth.resource_perm(COMMENT_URI, SERIES_ID, method, SERIES, action=orthanc_api.ORTHANC_ACTION_COMMENT))
			self.assertFalse(auth.resource_perm(DICOMWEB_COMMENT_URI, SERIES_ID, method, SERIES))
			self.assertFalse(auth.resource_perm(COMMENT_URI, SERIES_ID, method, orthanc_api.ORTHANC_SYSTEM))

		self.assertTrue(perm(comment_edit=True).resource_perm(COMMENT_URI, SERIES_ID, 'POST', SERIES, action=orthanc_api.ORTHANC_ACTION_COMMENT))

	def test_resource_delete_still_requires_remove(self):
		self.assertFalse(perm(view=True, comment_edit=True, remove=False).resource_perm(SERIES_ID, SERIES_ID, 'DELETE', SERIES))
		self.assertTrue(perm(view=True, comment_edit=False, remove=True).resource_perm(SERIES_ID, SERIES_ID, 'DELETE', SERIES))

	def test_ancestor_traversal_for_comment_actions_still_needs_view(self):
		self.assertTrue(perm(view=True).resource_perm('', SERIES_ID, 'DELETE', orthanc_api.ORTHANC_RESOURCE_STUDY,
			action=orthanc_api.ORTHANC_ACTION_COMMENT))
		self.assertFalse(perm(view=False, remove=True).resource_perm('', SERIES_ID, 'DELETE', orthanc_api.ORTHANC_RESOURCE_STUDY,
			action=orthanc_api.ORTHANC_ACTION_COMMENT))


class CommentRemovalPolicyCompositionTests(TestCase):
	"""	The group-policy method composes a local (Orthanc) policy with the global policy. For a
		comment DELETE the two arms are independent: a local CommentEdit deny vetoes the
		comment-management arm but leaves a global `remove` grant able to admit the request.
	"""

	def setUp(self):
		from django.contrib.auth.models import Group, User

		from ..auth.models.auth import PacsImagingServerGroupAuthorization
		from ..models import PacsImagingServer

		self.user = User.objects.create_user('alice')
		self.group = Group.objects.create(name='comment-policy-tests')
		self.group.user_set.add(self.user)
		self.server = PacsImagingServer(name='policy-test-server')
		self.auth_class = PacsImagingServerGroupAuthorization

	def _policy(self, **grants):
		defaults = dict(server=self.server, group=self.group, resource='*', view=True, comment_view=True)
		defaults.update(grants)
		return self.auth_class(**defaults)

	def _delete(self, policy, local, resource=COMMENT_URI, action=orthanc_api.ORTHANC_ACTION_COMMENT):
		with mock.patch.object(self.auth_class, 'orthanc_resource_auth', return_value=local):
			return policy.user_has_perm(self.user, resource, SERIES_ID, 'DELETE', SERIES, action=action)

	def test_global_remove_survives_a_local_comment_edit_deny(self):
		policy = self._policy(comment_edit=True, remove=True)
		local = { 'view': True, 'comment_view': True, 'comment_edit': False }

		self.assertTrue(self._delete(policy, local))
		self.assertTrue(self._delete(policy, local, resource=DICOMWEB_COMMENT_URI, action=None))

	def test_local_comment_edit_deny_still_vetoes_the_comment_management_arm(self):
		policy = self._policy(comment_edit=True, remove=False)
		local = { 'view': True, 'comment_view': True, 'comment_edit': False }

		self.assertFalse(self._delete(policy, local))
		self.assertFalse(self._delete(policy, local, resource=DICOMWEB_COMMENT_URI, action=None))

		with mock.patch.object(self.auth_class, 'orthanc_resource_auth', return_value=local):
			for method in ('POST', 'PUT'):
				self.assertFalse(policy.user_has_perm(self.user, COMMENT_URI, SERIES_ID, method, SERIES,
					action=orthanc_api.ORTHANC_ACTION_COMMENT))

	def test_local_remove_grant_admits_comment_delete_on_its_own(self):
		policy = self._policy(comment_edit=False, remove=False)
		local = { 'view': True, 'comment_view': True, 'comment_edit': False, 'remove': True }

		self.assertTrue(self._delete(policy, local))

	def test_local_comment_view_deny_still_blocks_reads(self):
		policy = self._policy(comment_edit=True, remove=True)
		local = { 'view': True, 'comment_view': False }

		with mock.patch.object(self.auth_class, 'orthanc_resource_auth', return_value=local):
			self.assertFalse(policy.user_has_perm(self.user, COMMENT_URI, SERIES_ID, 'GET', SERIES,
				action=orthanc_api.ORTHANC_ACTION_COMMENT))

	def test_no_local_policy_defers_to_the_global_policy(self):
		self.assertTrue(self._delete(self._policy(comment_edit=False, remove=True), None))
		self.assertTrue(self._delete(self._policy(comment_edit=True, remove=False), None))
		self.assertFalse(self._delete(self._policy(comment_edit=False, remove=False), None))
