"""	Resource permission lookup (`resource-acl`) for superusers and policy members.

	The Orthanc comment endpoint reads `remove` from this lookup to decide whether a user may remove
	another user's comment, so the lookup must agree with the authorization decision in front of it:
	a superuser holds every resource permission there, and must hold every one here.
"""
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import Group, User
from django.test import TestCase

from orthancapi import apisettings as orthanc_api

from ..auth.models.auth import PacsImagingServerGroupAuthorization
from ..auth.views.service.orthanc_resource import OrthancResourceAclIntrospectionView
from ..models import PacsImagingServer


STUDY_ID = '67110e78-66f6fcca-6b3b9eaf-aa98fa62-0dd3a6e6'
STUDY = orthanc_api.ORTHANC_RESOURCE_STUDY


class ResourceAclPermissionLookupTests(TestCase):

	def setUp(self):
		self.server = PacsImagingServer.objects.create(name='resource-acl-server')
		self.group = Group.objects.create(name='research')
		PacsImagingServerGroupAuthorization.objects.create(
			server=self.server, group=self.group, resource='*', comment_edit=True)

		self.admin = User.objects.create_superuser('admin', 'admin@example.org', 'pw')
		self.member = User.objects.create_user('member', 'member@example.org')
		for user in (self.admin, self.member):
			user.groups.add(self.group)

	def _lookup(self, user, local=None):
		data = { 'level': STUDY, 'orthanc_id': STUDY_ID, 'method': 'get' }
		view = OrthancResourceAclIntrospectionView()
		view.form = SimpleNamespace(
			server=self.server, user=user, data=data, cleaned_data=data, is_valid=lambda: True)

		with mock.patch.object(PacsImagingServerGroupAuthorization, 'orthanc_resource_auth',
				return_value=local or {}) as local_lookup:
			adata = view.get_authorization_response({})

		return adata['perms'], local_lookup

	def test_superuser_holds_every_resource_permission(self):
		perms, local_lookup = self._lookup(self.admin)

		self.assertEqual(perms, dict((_rp, True) for _rp in orthanc_api.SONADOR_RESOURCE_PERMS))
		local_lookup.assert_not_called()

	def test_superuser_outside_every_group_holds_every_resource_permission(self):
		self.admin.groups.clear()
		perms, _ = self._lookup(self.admin)

		self.assertTrue(all(perms.values()))

	def test_member_gets_only_what_policies_grant(self):
		perms, _ = self._lookup(self.member)

		self.assertTrue(perms['comment_edit'])
		self.assertFalse(perms['remove'])
		self.assertFalse(perms['view'])

	def test_member_local_grants_are_merged(self):
		perms, _ = self._lookup(self.member, local={ 'view': True, 'remove': True })

		self.assertTrue(perms['view'])
		self.assertTrue(perms['remove'])
		self.assertFalse(perms['modify'])
