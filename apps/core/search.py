import logging

from django import forms
from guru.errors import ConfigurationError
from guru.helpers.utils.object import pick, omit

from .views import SonadorApiObjectMixin, JSONFormApiView

logger = logging.getLogger(__name__)


class SonadorUnifiedSearchForm(forms.Form):
	'''	Search form which can be used to execute a full text search across multiple models. Results
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
	searchmodels = None
	searchmodel_filter_fieldmap = {}
	searchmodel_search_type = {}
	search_type_default = 'websearch'
	
	filterkey_transforms = {}

	# Search term
	term = forms.CharField(required=True)

	def __init__(self, *args, **kwargs):
		self.searchmodels = kwargs.pop('searchmodels', self.searchmodels)
		self.searchmodel_filter_fieldmap = kwargs.pop('searchmodel_filter_fieldmap', self.searchmodel_filter_fieldmap)
		self.searchmodel_search_type = kwargs.pop('searchmodel_search_type', self.searchmodel_search_type)
		self.search_type_default = kwargs.pop('search_type_default', self.search_type_default)

		# Ensure that searchmodels is defined 
		if not self.searchmodels:
			raise ConfigurationError('Unable to initialize search form instance, invalid searh models instance')

		# Ensure that the models in the search implement "search" and "json" methods, which are required by the interface
		for _m in self.searchmodels.values():

			# Check for search method on object manager
			if not callable(getattr(_m.objects, 'search', None)):
				raise ConfigurationError('Unable to initialize search form instance, model "%s" does not provide a search method')

			# Check for json method on model class
			if not getattr(_m, 'json', None):
				raise ConfigurationError('Unable to initialize search form instance, model "%s"')

		# If filterkey transforms are defined, make sure that they include a model mapping in dot notation.
		# Model mappings should be {model}.{transform}.
		if self.filterkey_transforms:

			for _t in self.filterkey_transforms.keys():
				_model_str, _transform_str = _t.split('.')

				# Ensure that the model string is found in the search models
				if not _model_str in self.searchmodels.keys():
					raise KeyError('Invalid transform, model "%s" not associated with the form' % _model_str)

		super().__init__(*args, **kwargs)

	def clean(self, *args, **kwargs):
		cleaned_data = super().clean(*args, **kwargs)
		return cleaned_data

	def _get_filter_params(self, mlabel):
		'''	Retrieve filter parameters for the provided model label
		'''
		# Retrieve filter paramters from the form data
		fparams = pick(self.cleaned_data, self.searchmodel_filter_fieldmap.get(mlabel, tuple()))

		# Transform filter parameters based on rules in filterkey_transforms
		for fkey, fval in list(fparams.items()):

			# Create model prefixed version of field key to check for transform
			_model_fkey = '%s.%s' % (mlabel, fkey)

			# Re-write key to form requried by the query-set API
			if _model_fkey in self.filterkey_transforms:
				fparams[self.filterkey_transforms.get(_model_fkey)] = fparams.pop(fkey)

		return fparams

	def execute_search(self, results=None):
		'''	Execute the search

			@input results (iterable, default=new results list): list of results

			@returns results
		'''
		# Ensure that the model is valid
		if not self.is_valid():
			raise ValueError('Unable to execute search, form data is not valid')

		# Execute model searches
		results = results or []
		for _mlabel, _model in self.searchmodels.items():

			# Retrieve filter parameters from the form data
			fparams = self._get_filter_params(_mlabel)

			# Execute search
			results.extend(
				_model.objects.search(self.cleaned_data.get('term', ''), qs=_model.objects.filter(**fparams) if fparams else None,
					search_type=self.searchmodel_search_type.get(_mlabel, self.search_type_default)))

		return results


class SonadorUnifiedSearchView(JSONFormApiView):
	'''	View class which can be used to execute full text search across multiple models. Results
		are aggregated, sorted by relevance, and returned as a single iterable.

		@property formclass (SonadorUnifiedSearchForm or subclass): search form which is used 
			to execute the search.
	'''
	formclass = None

	def getModelJsonData(self, instance, request, *args, **kwargs):
		'''	Serialize model instance to JSON and specify the result type
		'''
		data = instance.json
		data['rank'] = getattr(instance, 'rank', 0)

		# Add result type to JSON
		if self.searchmodel_types.get(type(instance)):
			data['result-type'] = self.searchmodel_types.get(type(instance))

		return data

	def get_data(self, context):
		'''	Execute the form search and return the results list
		'''
		response = super().get_data(context)

		# Retrieve 
		form = context.get('form') or self.get_form()
		if form.is_valid():

			# Create reverse mapping of result types
			setattr(self, 'searchmodel_types', dict((v,k) for k,v in form.searchmodels.items()))

			# Transform results to JSON
			response['results'] = list(sorted(
				[self.getModelJsonData(_r, self.request) for _r in form.execute_search()],
				key= lambda _r: _r.get('rank', 0), reverse=True))

		return response