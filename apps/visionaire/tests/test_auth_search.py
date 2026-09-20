'''	Unified user/group search behind the Share Access dialog: each user and each group appears
	once in the results, however many group memberships or server authorizations matched.
'''
import json

from django.contrib.auth.models import Group, User
from django.test import TestCase

from ..auth.models.auth import PacsImagingServerGroupAuthorization
from ..auth.models.user import SonadorProxyUser, SonadorProxyGroup
from ..auth.views.user import PacsImagingUnifiedAuthModelSearchForm
from ..models import PacsImagingServer


class _Principal:
	def __init__(self, pk, rank=0):
		self.pk, self.rank = pk, rank


class UniquePrincipalsHelperTests(TestCase):
	'''	The de-duplication step applied to every search result list
	'''
	def test_keeps_one_entry_per_principal_with_the_highest_rank(self):
		low, high, other = _Principal(1, 0.2), _Principal(1, 0.9), _Principal(2, 0.5)

		kept = PacsImagingUnifiedAuthModelSearchForm._unique_principals([low, other, high])

		self.assertEqual([(p.pk, p.rank) for p in kept], [(1, 0.9), (2, 0.5)])

	def test_same_pk_on_different_models_are_different_principals(self):
		class _Group(_Principal): pass

		kept = PacsImagingUnifiedAuthModelSearchForm._unique_principals([_Principal(1), _Group(1)])

		self.assertEqual(len(kept), 2)


class UnifiedAuthSearchTests(TestCase):
	'''	Searches run against the database (PostgreSQL full-text search), through the model
		managers, the form and the HTTP endpoint.
	'''
	def setUp(self):
		self.server = PacsImagingServer.objects.create(name='search-test-server')
		self.research = self._group('oaktree.tech-research')
		self.consult = self._group('oaktree-tech.consult')

		self.admin = User.objects.create_superuser('search-admin', 'admin@example.org', 'search-admin-pw')

		# Matched through the username AND through one of two authorized groups
		self.user = User.objects.create_user('research-user', 'research@example.org')
		self.user.groups.add(self.research, self.consult)

		# Matched through the username only (a single authorized group that does not match)
		self.control = User.objects.create_user('research-control', 'control@example.org')
		self.control.groups.add(self.consult)

	def _group(self, name):
		group = Group.objects.create(name=name)
		PacsImagingServerGroupAuthorization.objects.create(server=self.server, group=group, view=True)
		return group

	def _search(self, term):
		form = PacsImagingUnifiedAuthModelSearchForm(data={ 'term': term }, server=self.server, user=self.admin)
		self.assertTrue(form.is_valid(), form.errors)
		return form.execute_search()

	@staticmethod
	def _keys(results):
		return [(type(r).__name__, r.pk) for r in results]

	def _assert_unique(self, results):
		keys = self._keys(results)
		self.assertEqual(len(keys), len(set(keys)), 'A principal was listed more than once: %s' % keys)

	# Model managers

	def test_user_manager_lists_a_user_once_with_the_best_rank(self):
		qs = SonadorProxyUser.objects.filter(groups__server_authorizations__server=self.server)

		found = { u.username: u for u in SonadorProxyUser.objects.search('research', qs=qs) }
		usernames = [u.username for u in SonadorProxyUser.objects.search('research', qs=qs)]

		self.assertEqual(sorted(usernames), ['research-control', 'research-user'])
		self.assertGreater(found['research-user'].rank, found['research-control'].rank,
			'The rank kept for a user must be the best across their memberships, not an arbitrary one')

	def test_user_manager_lists_a_user_once_when_every_membership_ranks_the_same(self):
		qs = SonadorProxyUser.objects.filter(groups__server_authorizations__server=self.server)

		usernames = [u.username for u in SonadorProxyUser.objects.search('research-user', qs=qs)]

		self.assertEqual(usernames, ['research-user'])

	def test_group_manager_lists_a_matching_group_once(self):
		qs = SonadorProxyGroup.objects.filter(server_authorizations__server=self.server)

		names = [g.name for g in SonadorProxyGroup.objects.search('research', qs=qs)]

		self.assertEqual(names, ['oaktree.tech-research'])

	# Form

	def test_form_lists_each_user_and_group_once(self):
		results = self._search('research')

		self._assert_unique(results)
		self.assertEqual([r.pk for r in results if isinstance(r, SonadorProxyUser) and r.username == 'research-user'], [self.user.pk])
		self.assertEqual([r.pk for r in results if isinstance(r, SonadorProxyGroup)], [self.research.pk])

	def test_form_fallback_search_lists_each_principal_once(self):
		# No full-text lexeme matches a prefix, so the form falls back to the icontains query
		results = self._search('resea')

		self.assertTrue(results, 'Expected the fallback query to find the research principals')
		self._assert_unique(results)
		self.assertIn(('SonadorProxyUser', self.user.pk), self._keys(results))
		self.assertIn(('SonadorProxyGroup', self.research.pk), self._keys(results))

	# Endpoint

	def test_endpoint_returns_each_principal_once_ordered_by_rank(self):
		self.client.force_login(self.admin)

		response = self.client.post('/visionaire/api/pacs/%s/auth/search/' % self.server.token,
			data=json.dumps({ 'term': 'research' }), content_type='application/json')

		self.assertEqual(response.status_code, 200, response.content)
		results = response.json()['results']
		keys = [(r['result-type'], r['id']) for r in results]
		self.assertEqual(len(keys), len(set(keys)), 'A principal was listed more than once: %s' % keys)
		self.assertEqual(keys.count(('user', self.user.pk)), 1)
		self.assertEqual(keys.count(('group', self.research.pk)), 1)
		self.assertEqual([r['rank'] for r in results], sorted((r['rank'] for r in results), reverse=True))
