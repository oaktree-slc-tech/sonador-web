from django.contrib.auth.models import User, Group
from django.db.models import Manager as DjangoModelManager

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
		
		# Execute search, filter by the manager search relevance, and return distinct entities
		return qs.annotate(rank=SearchRank(_vector, SearchQuery(query, search_type=search_type))) \
			.filter(rank__gte=self.search_relevance).distinct()


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

		# Search across group name
		_vector = SearchVector('name', weight='A')

		return qs.annotate(rank=SearchRank(_vector, SearchQuery(query, search_type=search_type))) \
			.filter(rank__gte=self.search_relevance).distinct()


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