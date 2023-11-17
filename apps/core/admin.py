from django.contrib.admin import AdminSite as DjangoAdminSite
from django.utils.translation import gettext_lazy


class SonadorAdminSite(DjangoAdminSite):
	'''	Django backend admin site for Sonador
	'''
	site_title = gettext_lazy('Sonador')
	site_header = gettext_lazy('Sonador Administration')
	index_title = gettext_lazy('Administration')
