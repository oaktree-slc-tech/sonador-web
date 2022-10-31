from django.shortcuts import reverse
from django.utils.html import format_html
from django.contrib import admin

from guru.helpers import gsetting
from guru.helpers.user import user_displayname

from secure.models import ApiAccess, ApiAccessToken
from secure.admin import ApiAccessAdmin, ApiAccessTokenAdmin

from ..auth.models import SocialAuthorizationServer, PacsImagingServerUserAuthorization, PacsImagingServerGroupAuthorization, \
	DataService
from ..models import PacsImagingServer, DicomImagingModality, RemoteDICOMwebServer 

from .auth import SonadorApiAccess, SonadorApiAccessToken, ProxySecureSocialAuthorizationServer, SocialAuthorizationServerAdmin, \
	ProxyDataService, DataServiceAdmin
from .servers import PacsImagingServerAdmin, ImagingServerAdminMixin


class UserLabelMixin(object):
	search_fields = ('user__username', 'user__first_name', 'user__last_name', 'user__email')
	autocomplete_fields = ('user',)

	def user_display(self, obj):
		return user_displayname(obj.user)
	user_display.short_description = ''

	def user_email(self, obj):
		return obj.user.email
	user_email.short_description = 'Email'


class SonadorApiAccessTokenAdmin(UserLabelMixin, ApiAccessTokenAdmin):
	'''	Admin to manage API tokens within Sonador
	'''
	list_display = ('user', 'user_display', 'user_email', 'admin_masked_token', 'description', 'ctime')


class SonadorApiAccessAdmin(UserLabelMixin, ApiAccessAdmin):
	'''	Admin to manage API access IDs and secrets within Sonador
	'''
	list_display = ('user', 'user_display', 'user_email', 'admin_masked_access_id', 'description', 'ctime')


# Authorization and authentication
admin.site.register(SonadorApiAccessToken, SonadorApiAccessTokenAdmin)
admin.site.register(ProxySecureSocialAuthorizationServer, SocialAuthorizationServerAdmin)
admin.site.register(SonadorApiAccess, SonadorApiAccessAdmin)
admin.site.register(ProxyDataService, DataServiceAdmin)


admin.site.register(PacsImagingServer, PacsImagingServerAdmin)
