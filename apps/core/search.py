import logging

from django import forms

from guru.errors import ConfigurationError
from guru.helpers.utils.object import pick, omit
from guru.filter.unified_search import GuruUnifiedSearchForm, GuruUnifiedSearchView

logger = logging.getLogger(__name__)


class SonadorUnifiedSearchForm(GuruUnifiedSearchForm):
	'''	Sonador search form which can be used to execute a full text search across multiple models. Results
		are aggregated, sorted by relevance, and returned as a single iterable.

		@property searchmodels (dict, required):  Dictionary of models to be included in form
			search results keyed to a string label.
		@property searchmodel_filter_fieldmap (dict): Dictionary of names which
			map form fields to the search model they are associated with. Form field data must be 
			explicitly mapped in order to be used for filtering search results.
		@propertry searchmodel_search_type (dict): Type of search query to execute.

		@property filterkey_transforms (dict, default=empty dict): Dictionary of filter key transforms
			which can be used to modify the name of the form field to a Django query set filter parameter. Example:

			{ 'user.username': 'username__icontains' }

			maps the filter form value 'username' (from the 'user' model) to the Django filter parameter 
			'username__icontains' that can be used to run a case-insensitive containerment test. Keys 
			must be the name of fields assigned to the form and must be prefixed with the model label provided in the search
			models argument. (Refer to the Django documentation for more information about the filter arguments supported
			by the Django Queryset API.)
	'''


class SonadorUnifiedSearchView(GuruUnifiedSearchView):
	'''	Sonador view class which can be used to execute full text search across multiple models. Results
		are aggregated, sorted by relevance, and returned as a single iterable.

		@property formclass (SonadorUnifiedSearchForm or subclass): search form which is used 
			to execute the search.
	'''