'''	Display Attributes permissions: the `display_attr` / `display_attr_modify` policy flags, the
	staff curation rule, the group search, and the display-attributes aggregate route allow-list.
'''
from django.contrib.auth.models import Group, User
from django.test import TestCase

from orthancapi import apisettings as orthanc_api
from orthancapi.auth.acl import ServerAuthorization

from ..auth.models.auth import PacsImagingServerGroupAuthorization
from ..auth.views.user import PacsImagingServerFrontendGroupFilterForm
from ..models import PacsImagingServer


GROUP = orthanc_api.ORTHANC_RESOURCE_GROUP


class DisplayAttrPermissionTests(TestCase):

	def setUp(self):
		self.server = PacsImagingServer.objects.create(name='display-attr-server')
		self.readers = Group.objects.create(name='readers')
		self.curators = Group.objects.create(name='curators')
		self.unattached = Group.objects.create(name='unattached')

		self.readers_policy = PacsImagingServerGroupAuthorization.objects.create(
			server=self.server, group=self.readers, display_attr=True, duration=30)
		self.curators_policy = PacsImagingServerGroupAuthorization.objects.create(
			server=self.server, group=self.curators, display_attr=True, display_attr_modify=True, tag=True)

		self.reader = User.objects.create_user('reader', 'reader@example.org')
		self.reader.groups.add(self.readers)

		self.curator = User.objects.create_user('curator', 'curator@example.org')
		self.curator.groups.add(self.curators)

		self.staff = User.objects.create_user('staff', 'staff@example.org', is_staff=True)
		self.inactive_staff = User.objects.create_user('staff-inactive', 'inactive@example.org', is_staff=True, is_active=False)

	def _perm(self, user, resource, method, orthanc_id=None, level=GROUP):
		granted, _ = self.server.user_has_perm(user, resource, orthanc_id, method, level)
		return granted

	def _collection(self, group):
		return '/groups/%d/display-attributes' % group.pk

	def _item(self, group):
		return '/groups/%d/display-attributes/8f1c2d3e-4a5b-4c6d-8e9f-0a1b2c3d4e5f' % group.pk

	# Member policies

	def test_reader_may_read_but_not_manage(self):
		self.assertTrue(self._perm(self.reader, self._collection(self.readers), 'GET', self.readers.pk))
		for method in ('POST', 'PUT', 'DELETE'):
			self.assertFalse(self._perm(self.reader, self._collection(self.readers), method, self.readers.pk), method)
			self.assertFalse(self._perm(self.reader, self._item(self.readers), method, self.readers.pk), method)

	def test_curator_may_read_and_manage(self):
		self.assertTrue(self._perm(self.curator, self._collection(self.curators), 'GET', self.curators.pk))
		self.assertTrue(self._perm(self.curator, self._collection(self.curators), 'POST', self.curators.pk))
		self.assertTrue(self._perm(self.curator, self._item(self.curators), 'PUT', self.curators.pk))
		self.assertTrue(self._perm(self.curator, self._item(self.curators), 'DELETE', self.curators.pk))

	def test_member_has_no_access_to_another_groups_collection(self):
		self.assertFalse(self._perm(self.curator, self._collection(self.readers), 'GET', self.readers.pk))
		self.assertFalse(self._perm(self.curator, self._collection(self.readers), 'POST', self.readers.pk))

	def test_display_attr_flags_do_not_grant_series_tags(self):
		readers_tags = '/groups/%d/tags' % self.readers.pk
		self.assertFalse(self._perm(self.reader, readers_tags, 'GET', self.readers.pk))

		# The curator policy grants `tag` but not `tag_modify`: the Group Tags manage flag must not leak in.
		curators_tags = '/groups/%d/tags' % self.curators.pk
		self.assertTrue(self._perm(self.curator, curators_tags, 'GET', self.curators.pk))
		self.assertFalse(self._perm(self.curator, curators_tags, 'POST', self.curators.pk))

	def test_series_tag_flags_do_not_grant_display_attrs(self):
		policy = PacsImagingServerGroupAuthorization.objects.create(
			server=self.server, group=self.unattached, tag=True, tag_modify=True)
		user = User.objects.create_user('tagger', 'tagger@example.org')
		user.groups.add(self.unattached)

		self.assertFalse(self._perm(user, self._collection(self.unattached), 'GET', self.unattached.pk))
		self.assertFalse(self._perm(user, self._collection(self.unattached), 'POST', self.unattached.pk))
		self.assertTrue(self._perm(user, '/groups/%d/tags' % self.unattached.pk, 'POST', self.unattached.pk))

	# Staff rule

	def test_staff_manage_every_group_with_a_policy(self):
		for group in (self.readers, self.curators):
			for method in ('GET', 'POST', 'PUT', 'DELETE'):
				self.assertTrue(self._perm(self.staff, self._collection(group), method, group.pk), (group.name, method))
				self.assertTrue(self._perm(self.staff, self._item(group), method, group.pk), (group.name, method))

	def test_staff_grant_carries_the_policy_duration(self):
		granted, duration = self.server.user_has_perm(self.staff, self._collection(self.readers), self.readers.pk, 'POST', GROUP)
		self.assertTrue(granted)
		self.assertEqual(duration, 30)

	def test_staff_are_denied_on_a_group_without_a_policy(self):
		self.assertFalse(self._perm(self.staff, self._collection(self.unattached), 'GET', self.unattached.pk))
		self.assertFalse(self._perm(self.staff, self._collection(self.unattached), 'POST', self.unattached.pk))

	def test_staff_are_denied_on_a_group_whose_policy_does_not_enable_display_attributes(self):
		PacsImagingServerGroupAuthorization.objects.create(server=self.server, group=self.unattached, tag=True)

		self.assertFalse(self._perm(self.staff, self._collection(self.unattached), 'GET', self.unattached.pk))
		self.assertFalse(self._perm(self.staff, self._collection(self.unattached), 'POST', self.unattached.pk))

	def test_superuser_without_memberships_is_reported_as_a_manager(self):
		admin = User.objects.create_superuser('da-admin', 'admin@example.org', 'pw')
		perms = self.server.server_perms(admin)

		self.assertTrue(perms['display_attr'])
		self.assertTrue(perms['display_attr_modify'])
		self.assertTrue(perms['is_superuser'])

	def test_staff_rule_is_scoped_to_the_display_attributes_route(self):
		self.assertFalse(self._perm(self.staff, '/groups/%d/tags' % self.readers.pk, 'GET', self.readers.pk))
		self.assertFalse(self._perm(self.staff, '/groups/%d/distortion-filter/devices' % self.readers.pk, 'GET', self.readers.pk))
		self.assertFalse(self._perm(self.staff, '/studies/abc', 'GET', 'abc', level='study'))

	def test_inactive_staff_are_denied(self):
		self.assertFalse(self._perm(self.inactive_staff, self._collection(self.readers), 'GET', self.readers.pk))

	# Reported permissions

	def test_server_perms_reports_member_flags(self):
		perms = self.server.server_perms(self.reader)
		self.assertTrue(perms['display_attr'])
		self.assertFalse(perms['display_attr_modify'])

		perms = self.server.server_perms(self.curator)
		self.assertTrue(perms['display_attr'])
		self.assertTrue(perms['display_attr_modify'])

	def test_server_perms_reports_both_flags_for_staff(self):
		perms = self.server.server_perms(self.staff)
		self.assertTrue(perms['display_attr'])
		self.assertTrue(perms['display_attr_modify'])
		self.assertFalse(perms['tag'])
		self.assertFalse(perms['tag_modify'])

	def test_policy_json_carries_both_flags(self):
		self.assertEqual(self.curators_policy.json['display_attr'], True)
		self.assertEqual(self.curators_policy.json['display_attr_modify'], True)
		self.assertEqual(self.readers_policy.json['display_attr_modify'], False)

	def test_flags_are_server_permissions(self):
		self.assertIn('display_attr', orthanc_api.SONADOR_SERVER_PERMS)
		self.assertIn('display_attr_modify', orthanc_api.SONADOR_SERVER_PERMS)

	# Aggregate route

	def test_aggregate_route_is_allowed_for_any_member(self):
		self.assertTrue(self._perm(self.reader, orthanc_api.ORTHANC_DISPLAY_ATTRS_AGGREGATE, 'GET', None, level='system'))

		plain = User.objects.create_user('plain', 'plain@example.org')
		plain.groups.add(self.unattached)
		PacsImagingServerGroupAuthorization.objects.create(server=self.server, group=self.unattached)
		self.assertTrue(self._perm(plain, orthanc_api.ORTHANC_DISPLAY_ATTRS_AGGREGATE, 'GET', None, level='system'))

	def test_aggregate_route_is_read_only_in_the_allow_list(self):
		auth = ServerAuthorization()
		self.assertTrue(auth.acl_scoped_resource(orthanc_api.ORTHANC_DISPLAY_ATTRS_AGGREGATE, 'GET'))
		self.assertIsNone(auth.acl_scoped_resource(orthanc_api.ORTHANC_DISPLAY_ATTRS_AGGREGATE, 'POST'))

	# Group search

	def _search(self, user, **filters):
		form = PacsImagingServerFrontendGroupFilterForm(data={ 'name': '', **filters }, server=self.server, user=user)
		self.assertTrue(form.is_valid(), form.errors)
		return sorted(group.name for group in form.execute_filter())

	def test_group_search_lists_only_enabled_groups_for_a_member(self):
		self.curator.groups.add(self.readers)
		PacsImagingServerGroupAuthorization.objects.create(server=self.server, group=self.unattached, tag=True)
		self.curator.groups.add(self.unattached)

		self.assertEqual(self._search(self.curator, display_attr=True), ['curators', 'readers'])
		self.assertEqual(self._search(self.curator, display_attr_modify=True), ['curators'])

	def test_group_search_for_staff_includes_enabled_groups_they_do_not_belong_to(self):
		PacsImagingServerGroupAuthorization.objects.create(server=self.server, group=self.unattached, tag=True)

		self.assertEqual(self._search(self.staff, display_attr=True), ['curators', 'readers'])
		self.assertEqual(self._search(self.staff), [])
		self.assertEqual(self._search(self.staff, tag=True), [])

	def test_route_regex_is_anchored(self):
		regex = orthanc_api.ORTHANC_GROUP_DISPLAY_ATTRS_REGEX
		self.assertTrue(regex.match('/groups/7/display-attributes'))
		self.assertTrue(regex.match('/groups/7/display-attributes/'))
		self.assertTrue(regex.match('/groups/7/display-attributes/8f1c2d3e-4a5b-4c6d-8e9f-0a1b2c3d4e5f'))
		self.assertIsNone(regex.match('/groups/7/display-attributesx'))
		self.assertIsNone(regex.match('/groups/7/tags'))
		self.assertIsNone(regex.match('/dicom-web/groups/7/display-attributes'))


class StaffNonMemberAccessTests(TestCase):
	'''	An active staff user who belongs to none of a server's groups reaches the server for
		display attribute curation: the profile and authorization endpoints answer, the aggregate
		and the enabled collections are granted, and nothing else is.
	'''
	def setUp(self):
		from secure.models import ApiAccessToken

		self.server = PacsImagingServer.objects.create(name='staff-access-server')
		self.readers = Group.objects.create(name='staff-access-readers')
		self.plain = Group.objects.create(name='staff-access-plain')
		self.readers_policy = PacsImagingServerGroupAuthorization.objects.create(
			server=self.server, group=self.readers, display_attr=True)
		self.plain_policy = PacsImagingServerGroupAuthorization.objects.create(
			server=self.server, group=self.plain)

		self.staff = User.objects.create_user('staff-nonmember', 'staff-nonmember@example.org', is_staff=True)
		self.staff_token = ApiAccessToken.objects.create(user=self.staff)

		# The Orthanc plugin authenticates to these endpoints as a superuser (basic auth, token as password)
		self.plugin = User.objects.create_user('plugin-account', 'plugin@example.org', is_superuser=True, is_staff=True)
		self.plugin_token = ApiAccessToken.objects.create(user=self.plugin)

	def _post(self, name, payload):
		import base64, json
		from django.urls import reverse

		credentials = base64.b64encode(('%s:%s' % (self.plugin.username, self.plugin_token.token)).encode()).decode()
		return self.client.post(reverse('auth-service:%s' % name, args=(self.server.pk,)), json.dumps(payload),
			content_type='application/json', HTTP_AUTHORIZATION='Basic %s' % credentials)

	def _credentials(self):
		return { 'token-key': 'api-token', 'token-value': self.staff_token.token }

	def _authorize(self, uri, method, level, orthanc_id=None):
		payload = dict(self._credentials(), uri=uri, method=method, level=level)
		if orthanc_id is not None:
			payload['orthanc-id'] = str(orthanc_id)
		return self._post('service-orthanc', payload)

	# Model

	def test_staff_has_access_when_a_policy_enables_display_attributes(self):
		self.assertTrue(self.server.user_has_access(self.staff))

	def test_staff_has_no_access_without_an_enabled_policy(self):
		self.readers_policy.display_attr = False
		self.readers_policy.save()
		self.assertFalse(self.server.user_has_access(self.staff))

		other = PacsImagingServer.objects.create(name='staff-access-other')
		self.assertFalse(other.user_has_access(self.staff))

	def test_inactive_staff_has_no_access(self):
		self.staff.is_active = False
		self.staff.save()
		self.assertFalse(self.server.user_has_access(self.staff))

	def test_staff_aggregate_and_enabled_collection_are_granted(self):
		granted, duration = self.server.user_has_perm(self.staff, orthanc_api.ORTHANC_DISPLAY_ATTRS_AGGREGATE, None, 'GET', orthanc_api.ORTHANC_SYSTEM)
		self.assertTrue(granted)
		self.assertEqual(duration, self.readers_policy.duration)
		# The catalogue the editor's search reads
		granted, duration = self.server.user_has_perm(self.staff, orthanc_api.ORTHANC_CACHE_TAGS, None, 'GET', orthanc_api.ORTHANC_SYSTEM)
		self.assertTrue(granted)
		self.assertEqual(duration, self.readers_policy.duration)

	def test_staff_scope_grant_carries_the_shortest_enabled_duration(self):
		'''	A disabled policy must take effect within the same window as a member's grant, so the
			server-wide grants carry the shortest duration among the enabled policies.
		'''
		longer = Group.objects.create(name='staff-access-longer')
		PacsImagingServerGroupAuthorization.objects.create(server=self.server, group=longer, display_attr=True, duration=600)
		self.readers_policy.duration = 20
		self.readers_policy.save()

		_, duration = self.server.user_has_perm(self.staff, orthanc_api.ORTHANC_CACHE_TAGS, None, 'GET', orthanc_api.ORTHANC_SYSTEM)
		self.assertEqual(duration, 20)
		granted, _ = self.server.user_has_perm(self.staff, '/groups/%d/display-attributes' % self.readers.pk, self.readers.pk, 'POST', GROUP)
		self.assertTrue(granted)

	def test_staff_grant_stops_at_display_attributes(self):
		denied = (
			(orthanc_api.ORTHANC_DISPLAY_ATTRS_AGGREGATE, 'POST', orthanc_api.ORTHANC_SYSTEM, None),
			(orthanc_api.ORTHANC_CACHE_TAGS, 'POST', orthanc_api.ORTHANC_SYSTEM, None),
			(orthanc_api.ORTHANC_CACHE_TAGS, 'PUT', orthanc_api.ORTHANC_SYSTEM, None),
			(orthanc_api.ORTHANC_CACHE_TAGS, 'DELETE', orthanc_api.ORTHANC_SYSTEM, None),
			('/cache/studies', 'GET', orthanc_api.ORTHANC_SYSTEM, None),
			('/groups/%d/display-attributes' % self.plain.pk, 'GET', GROUP, self.plain.pk),
			('/groups/%d/tags' % self.readers.pk, 'GET', GROUP, self.readers.pk),
			('/groups/%d' % self.readers.pk, 'GET', GROUP, self.readers.pk),
			('/dicom-web/studies', 'GET', orthanc_api.ORTHANC_SYSTEM, None),
			('/studies/abc', 'GET', 'study', 'abc'),
		)
		for resource, method, level, orthanc_id in denied:
			granted, _ = self.server.user_has_perm(self.staff, resource, orthanc_id, method, level)
			self.assertFalse(granted, '%s %s was granted' % (method, resource))

	def test_staff_aggregate_and_catalogue_need_an_enabled_policy(self):
		self.readers_policy.display_attr = False
		self.readers_policy.save()
		for resource in (orthanc_api.ORTHANC_DISPLAY_ATTRS_AGGREGATE, orthanc_api.ORTHANC_CACHE_TAGS):
			granted, _ = self.server.user_has_perm(self.staff, resource, None, 'GET', orthanc_api.ORTHANC_SYSTEM)
			self.assertFalse(granted, resource)

	def test_inactive_staff_get_neither_aggregate_nor_catalogue(self):
		self.staff.is_active = False
		self.staff.save()
		for resource in (orthanc_api.ORTHANC_DISPLAY_ATTRS_AGGREGATE, orthanc_api.ORTHANC_CACHE_TAGS):
			granted, _ = self.server.user_has_perm(self.staff, resource, None, 'GET', orthanc_api.ORTHANC_SYSTEM)
			self.assertFalse(granted, resource)

	# Endpoints the plugin calls

	def _introspect(self):
		import json
		from django.urls import reverse

		# The management API authenticates the calling service by API token in the Authorization header
		response = self.client.post(reverse('visionaire-api:pacs-user-token-introspect', args=(self.server.pk,)),
			json.dumps(self._credentials()), content_type='application/json',
			HTTP_AUTHORIZATION='api-token %s' % self.plugin_token.token)
		return response, json.loads(response.content)

	def test_user_introspection_answers_for_non_member_staff(self):
		'''	The plugin builds its user context from this endpoint; a non-member staff user gets a profile
			that says they are staff with no groups and the display attribute permissions.
		'''
		response, body = self._introspect()

		self.assertEqual(response.status_code, 200, response.content)
		self.assertEqual(body['user']['username'], self.staff.username)
		self.assertTrue(body['user']['is_staff'])
		self.assertEqual(body['user']['groups'], [])
		self.assertIn(orthanc_api.SONADOR_PERM_DISPLAY_ATTR, body['user']['permissions'])
		self.assertIn(orthanc_api.SONADOR_PERM_DISPLAY_ATTR_MODIFY, body['user']['permissions'])

	def test_orthanc_profile_answers_for_non_member_staff(self):
		import json

		response = self._post('service-orthanc-user', self._credentials())
		body = json.loads(response.content)

		self.assertEqual(response.status_code, 200, response.content)
		self.assertEqual(body['name'], 'staff-nonmember')
		self.assertNotIn('all', body['permissions'])
		self.assertNotIn('*', body['authorized-labels'])

	def test_profiles_still_refuse_staff_without_an_enabled_policy(self):
		import json

		self.readers_policy.display_attr = False
		self.readers_policy.save()

		response, body = self._introspect()
		self.assertNotIn('user', body, response.content)

		response = self._post('service-orthanc-user', self._credentials())
		self.assertNotIn('name', json.loads(response.content), response.content)

		for uri in (orthanc_api.ORTHANC_DISPLAY_ATTRS_AGGREGATE, orthanc_api.ORTHANC_CACHE_TAGS):
			body = json.loads(self._authorize(uri, 'get', orthanc_api.ORTHANC_SYSTEM).content)
			self.assertFalse(body.get('granted'), '%s: %s' % (uri, body))

	def test_authorization_endpoint_grants_the_aggregate_and_enabled_collection(self):
		import json

		for uri, method, level, orthanc_id in (
				(orthanc_api.ORTHANC_DISPLAY_ATTRS_AGGREGATE, 'get', orthanc_api.ORTHANC_SYSTEM, None),
				(orthanc_api.ORTHANC_CACHE_TAGS, 'get', orthanc_api.ORTHANC_SYSTEM, None),
				('/groups/%d/display-attributes' % self.readers.pk, 'get', GROUP, self.readers.pk),
				('/groups/%d/display-attributes' % self.readers.pk, 'post', GROUP, self.readers.pk)):
			response = self._authorize(uri, method, level, orthanc_id)
			body = json.loads(response.content)
			self.assertEqual(response.status_code, 200, response.content)
			self.assertTrue(body.get('granted'), '%s %s: %s' % (method, uri, body))
			self.assertEqual(body.get('validity'), self.readers_policy.duration, '%s %s: %s' % (method, uri, body))

	def test_authorization_endpoint_denies_everything_else(self):
		import json

		for uri, method, level, orthanc_id in (
				(orthanc_api.ORTHANC_DISPLAY_ATTRS_AGGREGATE, 'post', orthanc_api.ORTHANC_SYSTEM, None),
				(orthanc_api.ORTHANC_CACHE_TAGS, 'post', orthanc_api.ORTHANC_SYSTEM, None),
				('/groups/%d/display-attributes' % self.plain.pk, 'get', GROUP, self.plain.pk),
				('/groups/%d/tags' % self.readers.pk, 'get', GROUP, self.readers.pk),
				('/dicom-web/studies', 'get', orthanc_api.ORTHANC_SYSTEM, None)):
			response = self._authorize(uri, method, level, orthanc_id)
			body = json.loads(response.content)
			self.assertFalse(body.get('granted'), '%s %s: %s' % (method, uri, body))

	# Viewer-side group search used by the Display Attributes tab

	def _search_groups(self, user, **filters):
		import json
		from django.urls import reverse

		self.client.force_login(user)
		response = self.client.post(reverse('visionaire-api:pacs-group-search', args=(self.server.pk,)), json.dumps(filters),
			content_type='application/json')
		self.client.logout()
		return response

	def test_group_search_lists_enabled_groups_for_non_member_staff(self):
		import json

		response = self._search_groups(self.staff, display_attr='true')

		self.assertEqual(response.status_code, 200, response.content)
		names = sorted(g['name'] for g in json.loads(response.content)['results'])
		self.assertEqual(names, [self.readers.name])

	def test_group_search_refuses_staff_without_an_enabled_policy(self):
		self.readers_policy.display_attr = False
		self.readers_policy.save()

		response = self._search_groups(self.staff, display_attr='true')

		self.assertEqual(response.status_code, 403, response.content)
