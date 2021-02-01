from django.shortcuts import reverse
from django.utils.html import format_html
from django.contrib import admin

from guru.helpers import gsetting

from secure.models import ApiAccess, ApiAccessToken
from secure.admin import ApiAccessAdmin, ApiAccessTokenAdmin

from .auth.models import SocialAuthorizationServer
from .models import PacsImagingServer, DicomImagingModality, RemoteDICOMwebServer


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
	list_display = ('server_id', 'name', 'active', 'hostname',  'port', 'description', 
		'admin_pacs_viewer', 'admin_pacs_server_admin', 'admin_pacs_server_dicomweb')

	def server_id(self, obj):
		return obj.pk
	server_id.short_description = 'Server ID'

	def admin_pacs_viewer(self, obj):
		'''	URL for PACS OHIF Viewer
		'''
		return format_html('<a href="{}" target="_blank">{}</a>', obj.url_viewer, 'Viewer')
	admin_pacs_viewer.short_description = ''

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


class ImagingServerAdminMixin(object):
	'''	Mixin instance which can be used to manage interactions with Orthanc API resources
	'''
	def get_readonly_fields(self, request, obj=None):
		rfields = super(ImagingServerAdminMixin, self).get_readonly_fields(request, obj=obj)
		if obj and obj.pk:
			rfields = ('server', 'name') + tuple(rfields)

		return rfields

class DicomImagingModalityAdmin(ImagingServerAdminMixin, admin.ModelAdmin):
	list_display = ('server', 'name', 'aet', 'host', 'port')
	list_filter = ('server',)


class RemoteDICOMWebServerAdmin(ImagingServerAdminMixin, admin.ModelAdmin):
	list_display = ('server', 'remoteserver_id', 'name', 'hostname', 'port', 'description')
	list_filter = ('server',)
	exclude = ('default',)

	def remoteserver_id(self, obj):
		return obj.pk
	remoteserver_id.short_description = 'Remote Server ID'


if gsetting('AUTH_ENABLED'):
	admin.site.register(ProxyApiAccessToken, ApiAccessTokenAdmin)
	admin.site.register(ProxySecureSocialAuthorizationServer, SocialAuthorizationServerAdmin)
	admin.site.register(ProxyApiAccess, ApiAccessAdmin)


admin.site.register(PacsImagingServer, PacsImaginServerAdmin)
admin.site.register(DicomImagingModality, DicomImagingModalityAdmin)
admin.site.register(RemoteDICOMwebServer, RemoteDICOMWebServerAdmin)
