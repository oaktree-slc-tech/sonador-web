import logging

from django import forms
from django.contrib.auth.models import Group

from guru.errors import ConfigurationError
from guru.forms import create_modelform_class
from core.forms import SonadorBaseForm

from guru import apisettings as gapi

from ...apisettings import WILDCARD
from ..models import PacsImagingServerGroupAuthorization
from ..helpers import parse_resource_policy

logger = logging.getLogger(__name__)



# Form classes for data validation
class PacsImagingServerGroupAuthorizationForm(SonadorBaseForm):
	''' Django form which can be used to validate group authorization grants
	'''
	def __init__(self, *args, server=None, **kwargs):
		self.server = server
		super().__init__(*args, **kwargs)

		if not self.server:
			raise ConfigurationError('Unable to initialize form instance, invalid imaging server reference: %s' % self.server)

	class Meta:
		model = PacsImagingServerGroupAuthorization
		exclude = ('token', 'server')

	def clean(self, *args, **kwargs):
		cleaned_data = super().clean(*args, **kwargs)

		# Prevent duplicate ACL policies for the same group from being created
		_group = cleaned_data.get('group')
		if _group and not getattr(self.instance, 'pk', None) and self.server.group_authorizations.filter(group=_group):			
			raise forms.ValidationError(
				"Authorization policy for group already exists", code=gapi.VALIDATION_APICODE_UNIQUE)

		# Ensure that a resource is present
		if not cleaned_data.get('resource'):
			raise forms.ValidationError('resource is a required field')

		# Ensure that resources can be parsed
		if cleaned_data.get('resource') and cleaned_data.get('resource') != WILDCARD:
			try: parse_resource_policy(cleaned_data.get('resource'))
			except Exception as err:
				raise forms.ValidationError(
					'Unable to parse "resource" to valid policy', code=gapi.VALIDATION_APICODE_INVALID)
		
		return cleaned_data