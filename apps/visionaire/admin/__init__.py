from django import forms
from django.shortcuts import reverse
from django.utils.html import format_html
from django.contrib import admin

from guru.helpers import gsetting
from guru.helpers.user import user_displayname

from secure.models import ApiAccess, ApiAccessToken
from secure.admin import ApiAccessAdmin, ApiAccessTokenAdmin

from content.widgets import CodeEditorAdminWidget

from ..auth.models import SocialAuthorizationServer, PacsImagingServerUserAuthorization, PacsImagingServerGroupAuthorization, \
	DataService
from ..models import PacsImagingServer, DicomImagingModality, RemoteDICOMwebServer 
from ..models.branding import SonadorSite

from .auth import SonadorApiAccess, SonadorApiAccessToken, ProxySecureSocialAuthorizationServer, \
	SocialAuthorizationServerSearchAdmin, SocialAuthorizationServerAdmin, \
	ProxyDataService, DataServiceAdmin
from .servers import PacsImagingServerAdmin, ImagingServerAdminMixin


# API Management

class UserLabelMixin(object):
	search_fields = ('user__username', 'user__first_name', 'user__last_name', 'user__email')
	autocomplete_fields = ('user',)

	@admin.display(
	    description=''
	)
	def user_display(self, obj):
		return user_displayname(obj.user)

	@admin.display(
	    description='Email'
	)
	def user_email(self, obj):
		return obj.user.email


@admin.register(SonadorApiAccessToken)
class SonadorApiAccessTokenAdmin(UserLabelMixin, ApiAccessTokenAdmin):
	'''	Admin to manage API tokens within Sonador
	'''
	list_display = ('user', 'user_display', 'user_email', 'admin_masked_token', 'description', 'ctime')


@admin.register(SonadorApiAccess)
class SonadorApiAccessAdmin(UserLabelMixin, ApiAccessAdmin):
	'''	Admin to manage API access IDs and secrets within Sonador
	'''
	list_display = ('user', 'user_display', 'user_email', 'admin_masked_access_id', 'description', 'ctime')


# Site Management


# Markdown message fields on SonadorSite which are edited with the ACE code editor
SONADORSITE_MARKDOWN_FIELDS = ('welcome', 'farewell')


class SonadorSiteAdminForm(forms.ModelForm):
	'''	ModelAdmin form which provides an ACE text editor for the site's markdown messages
		("Welcome" and "Farewell").
	'''
	class Meta:
		model = SonadorSite
		fields = '__all__'
		widgets = { field: CodeEditorAdminWidget(code_language='markdown') for field in SONADORSITE_MARKDOWN_FIELDS }

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		for field in SONADORSITE_MARKDOWN_FIELDS:
			self.fields[field].widget.attrs.update({ CodeEditorAdminWidget.code_language_attr: 'markdown' })


@admin.register(SonadorSite)
class SonadorSitesAdmin(admin.ModelAdmin):
	'''	Model admin instance for managing Sonador site instances	
	'''
	list_display = ('id', 'name', 'domain')

	fieldsets = (
		('Site Properties', { 'fields': ('name', 'domain')}),
		('Site Branding', { 'fields': ('logo', 'logo_narrow', 'favicon', 'welcome', 'farewell')})
	)

	form = SonadorSiteAdminForm


# Authorization and authentication
admin.site.register(SocialAuthorizationServer, SocialAuthorizationServerSearchAdmin)
admin.site.register(ProxySecureSocialAuthorizationServer, SocialAuthorizationServerAdmin)
admin.site.register(ProxyDataService, DataServiceAdmin)


# Site admin (replaces built-in Django Site Admin)


admin.site.register(PacsImagingServer, PacsImagingServerAdmin)
