from django.db import models
from django.contrib.sites.models import Site


class SonadorSite(Site):
	''' Subclass model for Site which provides a logo field
	'''
	logo = models.FileField(upload_to='sites/branding')


	class Meta:
		app_label = 'sites'
		verbose_name = 'Site'
		verbose_name_plural = 'Sites'
	