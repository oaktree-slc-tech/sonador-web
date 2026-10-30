"""	Superusers and staff are scoped to the imaging servers they are attached to.

	A superuser named by a user policy or a group policy on a server holds every permission there, and
	staff curate display attributes there. On a server that names them nowhere both are treated like
	any other unattached user: the server is not listed and its resources are refused.
"""
import base64
from types import SimpleNamespace

from django.contrib.auth.models import Group, User
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from orthancapi import apisettings as orthanc_api

from ..apisettings import SONADOR_PERMS, SONADOR_PERM_DISPLAY_ATTR, SONADOR_PERM_DISPLAY_ATTR_MODIFY
from ..auth.helpers import api_permission_imageserver_user_has_access, orthancserver_basicauth
from ..auth.models.auth import PacsImagingServerGroupAuthorization, PacsImagingServerUserAuthorization
from ..models import PacsImagingServer
from ..views.ohif import OhifDicomViewer
from ..views.servers import PacsImagingServerApiManagementView


STUDY_ID = '67110e78-66f6fcca-6b3b9eaf-aa98fa62-0dd3a6e6'
STUDY = orthanc_api.ORTHANC_RESOURCE_STUDY


class SuperuserServerScopeTests(TestCase):

	def setUp(self):
		self.attached = PacsImagingServer.objects.create(name='attached-server')
		self.unattached = PacsImagingServer.objects.create(name='unattached-server')
		self.inactive = PacsImagingServer.objects.create(name='inactive-server', active=False)

		self.group = Group.objects.create(name='research')
		PacsImagingServerGroupAuthorization.objects.create(server=self.attached, group=self.group, resource='*')
		PacsImagingServerGroupAuthorization.objects.create(
			server=self.unattached, group=Group.objects.create(name='others'), resource='*', view=True)

		self.admin = User.objects.create_superuser('admin', 'admin@example.org', 'pw')
		self.admin.groups.add(self.group)
		self.staff = User.objects.create_user('staffer', 'staffer@example.org', is_staff=True)

	def _view(self, user):
		return self.unattached.user_has_perm(user, '/studies/%s' % STUDY_ID, STUDY_ID, 'GET', STUDY)

	def test_attachment_through_a_group_or_a_user_policy(self):
		self.assertTrue(self.attached.user_is_attached(self.admin))
		self.assertFalse(self.unattached.user_is_attached(self.admin))

		PacsImagingServerUserAuthorization.objects.create(server=self.unattached, user=self.admin)
		self.assertTrue(self.unattached.user_is_attached(self.admin))

	def test_access_needs_attachment(self):
		self.assertTrue(self.attached.user_has_access(self.admin))
		self.assertFalse(self.unattached.user_has_access(self.admin))

	def test_authorization_bypass_needs_attachment(self):
		self.assertEqual(self.attached.user_has_perm(self.admin, '/studies/%s' % STUDY_ID, STUDY_ID, 'DELETE', STUDY),
			(True, None))
		self.assertEqual(self._view(self.admin), (False, None))

	def test_server_perms_follow_attachment(self):
		attached = self.attached.server_perms(self.admin)
		unattached = self.unattached.server_perms(self.admin)

		self.assertTrue(all(attached[p] for p in SONADOR_PERMS))
		# create_superuser makes the admin staff too; neither role reaches past attachment
		self.assertFalse(any(unattached[p] for p in SONADOR_PERMS))

	def test_superuser_attached_through_a_user_policy_holds_every_server_perm(self):
		PacsImagingServerUserAuthorization.objects.create(server=self.unattached, user=self.admin)

		self.assertTrue(all(self.unattached.server_perms(self.admin)[p] for p in SONADOR_PERMS))
		self.assertEqual(self._view(self.admin), (True, None))

	def test_viewer_lists_only_attached_servers(self):
		view = OhifDicomViewer()
		view.request = SimpleNamespace(user=self.admin)

		self.assertEqual(set(view.get_imaging_servers()), { self.attached })

	def test_server_api_lists_only_attached_servers_for_a_superuser(self):
		self.assertEqual(self._api_servers(self.admin), { self.attached })

	def test_server_api_lists_only_attached_servers_for_staff(self):
		self.assertEqual(self._api_servers(self.staff), set())

		PacsImagingServerUserAuthorization.objects.create(server=self.attached, user=self.staff)
		self.assertEqual(self._api_servers(self.staff), { self.attached })

	def test_staff_reach_only_attached_servers(self):
		# A display-attribute policy used to bring staff onto a server without attachment
		PacsImagingServerGroupAuthorization.objects.create(
			server=self.unattached, group=Group.objects.create(name='curators'), display_attr=True)

		self.assertFalse(self.unattached.user_has_access(self.staff))
		self.assertFalse(api_permission_imageserver_user_has_access(
			self.staff, None, (), { 'serverid': self.unattached.pk }, server_url_param='serverid'))
		perms = self.unattached.server_perms(self.staff)
		self.assertFalse(perms[SONADOR_PERM_DISPLAY_ATTR] or perms[SONADOR_PERM_DISPLAY_ATTR_MODIFY])

		PacsImagingServerUserAuthorization.objects.create(server=self.unattached, user=self.staff)
		self.assertTrue(self.unattached.user_has_access(self.staff))
		self.assertTrue(self.unattached.server_perms(self.staff)[SONADOR_PERM_DISPLAY_ATTR_MODIFY])

	def test_server_api_helper_needs_attachment(self):
		check = lambda server: api_permission_imageserver_user_has_access(
			self.admin, None, (), { 'serverid': server.pk }, server_url_param='serverid')

		self.assertTrue(check(self.attached))
		self.assertFalse(check(self.unattached))

	def _api_servers(self, user):
		view = PacsImagingServerApiManagementView()
		view.request = RequestFactory().get('/visionaire/api/pacs')
		view.request.user = user
		view.kwargs = {}

		return set(view.getQueryset())


class ServiceAccountRouteTests(TestCase):
	'''	The Orthanc service routes authenticate a superuser service account by basic credentials. That
		account acts for the server, so it is not held to attachment; the user it asks about is.
	'''

	def setUp(self):
		from secure.models import ApiAccess

		self.server = PacsImagingServer.objects.create(name='service-server')
		self.service = User.objects.create_superuser('service', 'service@example.org', 'pw')
		self.access = ApiAccess.objects.create(user=self.service)

		self.route = orthancserver_basicauth(lambda user, request, vargs, vkwargs: user.is_superuser)(
			lambda request, *args, **kwargs: HttpResponse('ok'))

	def _call(self):
		credentials = base64.b64encode(('%s:%s' % (self.access.access_id, self.access.secret_key)).encode()).decode()
		request = RequestFactory().post('/', HTTP_AUTHORIZATION='Basic %s' % credentials)
		return self.route(request, serverid=self.server.pk)

	def test_unattached_superuser_service_account_is_admitted(self):
		self.assertFalse(self.server.user_is_attached(self.service))
		self.assertEqual(self._call().status_code, 200)

	def test_inactive_superuser_service_account_is_refused(self):
		self.service.is_active = False
		self.service.save()
		self.assertEqual(self._call().status_code, 403)
