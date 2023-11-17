from django.shortcuts import reverse
from django.utils.html import format_html
from django.contrib import admin

from guru.helpers import gsetting

from secure.models import ApiAccess, ApiAccessToken
from secure.admin import ApiAccessAdmin, ApiAccessTokenAdmin

from ..auth.models import SocialAuthorizationServer, PacsImagingServerGroupAuthorization
from ..models import PacsImagingServer, DicomImagingModality, RemoteDICOMwebServer


class PacsImagingServerGroupAuthorizationInline(admin.TabularInline):
	model = PacsImagingServerGroupAuthorization
	extra = 0
	autocomplete_fields = ('group',)


class DicomModalityAdminInline(admin.TabularInline):
	model = DicomImagingModality
	extra = 0


class RemoteDICOMWebServerAdminInline(admin.StackedInline):
	model = RemoteDICOMwebServer
	extra = 0
	exclude = ('default',)
	fields = (
		'name',
		('scheme', 'hostname', 'port'),
		'description',
		('username', 'password'),
	)


class PacsImagingServerAdmin(admin.ModelAdmin):
	'''	Admin instance for accessing and managing PACS servers from Sonador
	'''
	list_display = ('server_id', 'name', 'active', 'hostname',  'port', 'description',
		'admin_pacs_viewer', 'admin_pacs_server_admin', 'admin_pacs_server_dicomweb')
	list_filter = ('active',)
	search_fields = ('name', 'hostname', 'description')
	
	inlines = (PacsImagingServerGroupAuthorizationInline, DicomModalityAdminInline, RemoteDICOMWebServerAdminInline)

	@admin.display(
	    description='Server ID'
	)
	def server_id(self, obj):
		return obj.pk

	@admin.display(
	    description=''
	)
	def admin_pacs_viewer(self, obj):
		'''	URL for PACS OHIF Viewer
		'''
		return format_html('<a href="{}" target="_blank">{}</a>', obj.url_viewer, 'Viewer')

	@admin.display(
	    description=''
	)
	def admin_pacs_server_admin(self, obj):
		'''	URL for PACS server administration
		'''
		return format_html('<a href="{}" target="_blank">{}</a>',
				reverse('auth-service:orthanc-admin-redirect', args=(obj.pk,)) if gsetting('AUTH_ENABLED') else obj.url_admin,
				'Admin',
			)

	@admin.display(
	    description=''
	)
	def admin_pacs_server_dicomweb(self, obj):
		'''	URL for PACS server dicom-web client
		'''
		return format_html('<a href="{}" target="_blank">{}</a>',
				reverse('auth-service:orthanc-dicomweb-redirect', args=(obj.pk,)) if gsetting('AUTH_ENABLED') else obj.url_admin,
				'DICOMweb Client',
			)


class ImagingServerAdminMixin(object):
	'''	Mixin instance which can be used to manage interactions with Orthanc API resources
	'''
	def get_readonly_fields(self, request, obj=None):
		rfields = super(ImagingServerAdminMixin, self).get_readonly_fields(request, obj=obj)
		if obj and obj.pk:
			rfields = ('server', 'name') + tuple(rfields)

		return rfields
