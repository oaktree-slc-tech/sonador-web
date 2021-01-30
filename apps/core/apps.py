from django.contrib.admin.apps import AdminConfig


class SonadorAdminConfig(AdminConfig):
	default_site = 'core.admin.SonadorAdminSite'
	