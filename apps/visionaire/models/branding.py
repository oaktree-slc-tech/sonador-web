from django.db import models
from django.contrib.sites.models import Site

from content.db import MarkupField


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

	class Meta:
		app_label = 'sites'
		verbose_name = 'Site'
		verbose_name_plural = 'Sites'
	