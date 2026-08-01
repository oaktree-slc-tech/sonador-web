from django.apps import AppConfig


class VisionaireAppConfig(AppConfig):
	'''	Configuration and overrides for the Visionaire App
	'''
	name = 'visionaire'
	default_auto_field = 'django.db.models.BigAutoField'

	def ready(self, *args, **kwargs):

		# Remove "Site" from model admin. The Visionaire app has it's own
		# Site admin which provides custom branding.
		from django.contrib import admin
		from django.contrib.sites.models import Site
		admin.site.unregister(Site)

		# Initialize Visionaire app components
		super().ready(*args, **kwargs)

		# Enable Visionaire signals
		from . import signals

		# Enable authentication signals. Connects the receiver which revokes the identity
		# provider access token when a session ends.
		from .auth import signals as auth_signals