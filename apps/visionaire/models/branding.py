from django.db import models
from django.contrib.sites.models import Site

from content.db import MarkupField


class SonadorSite(Site):
	''' Subclass model for Site which provides a logo field
	'''
	logo = models.FileField(upload_to='sites/branding', null=True, blank=True)
	favicon = models.FileField(upload_to='sites/branding/favicon', null=True, blank=True)

	welcome = MarkupField(verbose_name='Welcome Message', markup_type='markdown', null=True, blank=True,
		help_text='Message displayed to new users who have not yet been granted to access to data or resources.')

	class Meta:
		app_label = 'sites'
		verbose_name = 'Site'
		verbose_name_plural = 'Sites'
	