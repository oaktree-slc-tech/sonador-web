from django.shortcuts import reverse
from django.utils.html import format_html
from django.contrib import admin

from django.templatetags.static import static

from guru.helpers import gsetting

from .models import ClinicalGateway, ClinicalGatewayVariable, GatewayImagingServer, GatewayDicomImagingModality


class GatewayVariableAdminInline(admin.TabularInline):
	model = ClinicalGatewayVariable
	extra = 0


class GatewayImagingServerAdminInline(admin.TabularInline):
	model = GatewayImagingServer
	extra = 0
	autocomplete_fields = ('server',)
	readonly_fields = ('active',)

	def active(self, obj):
		return format_html(
			'<img src="%s" alt="True" style="margin-top: -0.6rem;" />' 
				% (static('admin/img/icon-yes.svg') if obj.server.active else static('admin/img/icon-no.svg')))


class GatewayDicomModalityAdminInline(admin.TabularInline):
	model = GatewayDicomImagingModality
	extra = 0


@admin.register(ClinicalGateway)
class ClinicalGatewayAdmin(admin.ModelAdmin):
	'''	Admin instance for accessing and managing Clinical Gateway Instances
	'''
	list_display = ('gateway_id', 'name', 'description', 'user', 'active')
	list_filter = ('active',)
	search_fields = ('token', 'name', 'description', 
		'user__username', 'user__first_name', 'user__last_name', 'user__email')
	autocomplete_fields = ('user',)

	inlines = (GatewayVariableAdminInline, GatewayImagingServerAdminInline, GatewayDicomModalityAdminInline)

	@admin.display(
	    description='Gateway ID'
	)
	def gateway_id(self, obj):
		return obj.pk


