from django.contrib.admin import AdminSite as DjangoAdminSite
from django.utils.translation import ugettext_lazy


class SonadorAdminSite(DjangoAdminSite):
	'''	Django backend admin site for Sonador
	'''
	site_title = ugettext_lazy('Sonador')
	site_header = ugettext_lazy('Sonador Administration')
	index_title = ugettext_lazy('Administration')
