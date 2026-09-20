from django.contrib.auth.models import User, Group
from django.db.models import Manager as DjangoModelManager, Max

from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank

from guru.helpers.utils.object import pick
from guru.helpers.user import user_displayname


class SonadorUserSearchManager(DjangoModelManager):
	'''	Django ORM manager that is able to execute full text search queries on the Django user model
	'''
	search_relevance = 0.1

	def search(self, query, qs=None, search_type='websearch'):
		qs = qs or self.get_queryset()

		# Search across username, first_name, last_name, email, and group names
		_vector = SearchVector('username', weight='A') + SearchVector('email', weight='A') \
			+ SearchVector('first_name', weight='B') + SearchVector('last_name', weight='B') \
			+ SearchVector('groups__name', weight='C')

		# The group-name vector joins one row per group membership (and one per server authorization
		# of that group when the caller filters on it), each ranked against its own group name. Rank
		# is aggregated per user so that a user matched through several groups, or through both a
		# profile field and a group, is returned once with the best of those ranks.
		return qs.annotate(rank=Max(SearchRank(_vector, SearchQuery(query, search_type=search_type)))) \
			.filter(rank__gte=self.search_relevance)


class SonadorProxyUser(User):
	'''	Proxy user model which provides a search manager able to execute search quries
	'''
	objects = SonadorUserSearchManager()

	class Meta:
		proxy = True

	@property
	def json(self):
		'''	JSON properties for user
		'''
		_data = pick(self, ('id', 'username', 'email', 'first_name', 'last_name'))
		_data['label_user'] = user_displayname(self)
		return _data


class SonadorGroupSearchManager(DjangoModelManager):
	'''	Django ORM manager that is able to execute full text search queries on the Django group model
	'''	
	search_relevance = 0.1

	def search(self, query, qs=None, search_type='websearch'):
		qs = qs or self.get_queryset()

		# Search across group name; rank is aggregated per group so a caller's join (for example
		# on server authorizations) cannot repeat a group in the results
		_vector = SearchVector('name', weight='A')

		return qs.annotate(rank=Max(SearchRank(_vector, SearchQuery(query, search_type=search_type)))) \
			.filter(rank__gte=self.search_relevance)


class SonadorProxyGroup(Group):
	'''	Proxy group model which provides a search manager able to execute search queries
	'''
	objects = SonadorGroupSearchManager()

	class Meta:
		proxy = True

	@property
	def json(self):
		'''	JSON properties for group
		'''
		return pick(self, ('id', 'name'))