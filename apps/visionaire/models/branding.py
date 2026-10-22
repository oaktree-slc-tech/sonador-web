from django.db import models
from django.contrib.sites.models import Site

from content.db import MarkupField

from ..apisettings.display_attrs import default_display_attributes, clean_display_attributes


class SonadorSite(Site):
	''' Subclass model for Site which provides a logo field
	'''
	logo = models.FileField(upload_to='sites/branding', null=True, blank=True)

	logo_narrow = models.FileField(upload_to='sites/branding', null=True, blank=True,
		verbose_name='Narrow Logo',
		help_text='Square mark shown when the viewer sidebar is collapsed. Recommended 64x64.')

	favicon = models.FileField(upload_to='sites/branding/favicon', null=True, blank=True)

	welcome = MarkupField(verbose_name='Welcome Message', markup_type='markdown', null=True, blank=True,
		help_text='Message displayed to new users who have not yet been granted to access to data or resources.')

	farewell = MarkupField(verbose_name='Farewell Message', markup_type='markdown', null=True, blank=True,
		help_text='Message displayed on the sign-out confirmation page after a user ends their session.')

	display_attributes = models.JSONField(verbose_name='Display Attributes', default=default_display_attributes, blank=True,
		validators=[clean_display_attributes],
		help_text='Default display properties for viewer tools, keyed by tool name.')

	def save(self, *args, **kwargs):
		'''	Store display attributes in canonical form (`#RRGGBB` colors)
		'''
		self.display_attributes = clean_display_attributes(self.display_attributes)
		return super().save(*args, **kwargs)

	class Meta:
		app_label = 'sites'
		verbose_name = 'Site'
		verbose_name_plural = 'Sites'
	