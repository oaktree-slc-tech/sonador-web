from django.shortcuts import reverse
from django.utils.html import format_html
from django.contrib import admin

from guru.helpers import gsetting

from secure.models import ApiAccess, ApiAccessToken
from secure.admin import ApiAccessAdmin, ApiAccessTokenAdmin

from .auth.models import SocialAuthorizationServer
from .models import PacsImagingServer


class ProxyApiAccess(ApiAccess):
	'''	Proxy model which allows for the API access (access ID/secret) to appear in the same model
		as groups and auth servers
	'''
	class Meta:
		app_label = 'auth'
		proxy = True
		verbose_name = 'API Access'
		verbose_name_plural = 'Access IDs/Secret Keys'


class ProxyApiAccessToken(ApiAccessToken):
	'''	Proxy model which allows for API access tokens to appear in the same model
		as groups and auth servers.
	'''
	class Meta:
		app_label = 'auth'
		proxy = True
		verbose_name = 'API Access Token'
		verbose_name_plural = 'API Access Tokens'


class ProxySecureSocialAuthorizationServer(SocialAuthorizationServer):
	'''	Proxy model which allows for the social authorization server to appear
		in the same admin group as API and Accesz Tokens
	'''
	class Meta:
		app_label = 'auth'
		proxy = True
		verbose_name = 'Auth Server'
		verbose_name_plural = 'Authentication Servers'


class SocialAuthorizationServerAdmin(admin.ModelAdmin):
    list_display = ('token', 'provider', 'description', 'url_login', 'url_callback', 'default')


class PacsImaginServerAdmin(admin.ModelAdmin):
	'''	Admin instance for accessing and managing PACS servers from Sonador
	'''
	list_display = ('name', 'default', 'hostname',  'port', 'description', 'admin_pacs_server_admin', 'admin_pacs_server_dicomweb')

	def admin_pacs_server_admin(self, obj):
		'''	URL for PACS server administration
		'''
		return format_html('<a href="{}" target="_blank">{}</a>', 
				reverse('auth-service:orthanc-admin-redirect', args=(obj.pk,)) if gsetting('AUTH_ENABLED') else obj.url_admin,
				'Admin',
			)
	admin_pacs_server_admin.short_description = ''

	def admin_pacs_server_dicomweb(self, obj):
		'''	URL for PACS server dicom-web client
		'''
		return format_html('<a href="{}" target="_blank">{}</a>',
				reverse('auth-service:orthanc-dicomweb-redirect', args=(obj.pk,)) if gsetting('AUTH_ENABLED') else obj.url_admin,
				'DICOMweb Client',
			)
	admin_pacs_server_dicomweb.short_description = ''


admin.site.register(ProxyApiAccessToken, ApiAccessTokenAdmin)
admin.site.register(ProxySecureSocialAuthorizationServer, SocialAuthorizationServerAdmin)
admin.site.register(PacsImagingServer, PacsImaginServerAdmin)
