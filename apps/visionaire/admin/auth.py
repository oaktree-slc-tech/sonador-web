from django.shortcuts import reverse
from django.utils.html import format_html
from django.contrib import admin

from guru.helpers import gsetting

from secure.models import ApiAccess, ApiAccessToken
from secure.admin import ApiAccessAdmin, ApiAccessTokenAdmin

from ..auth.models import SocialAuthorizationServer, PacsImagingServerUserAuthorization, PacsImagingServerGroupAuthorization
from ..models import PacsImagingServer, DicomImagingModality, RemoteDICOMwebServer


class ProxyApiAccess(ApiAccess):
	'''	Proxy model which allows for the API access (access ID/secret) to appear in the same model
		as groups and auth servers
	'''
	class Meta:
		app_label = 'auth'
		proxy = True
		verbose_name = 'API Access'
		verbose_name_plural = 'Access IDs/Secret Keys'
	
	def __str__(self):
		return '%s... (user=%s)' % (self.access_id[:15], self.user.username)


class ProxyApiAccessToken(ApiAccessToken):
	'''	Proxy model which allows for API access tokens to appear in the same model
		as groups and auth servers.
	'''
	class Meta:
		app_label = 'auth'
		proxy = True
		verbose_name = 'API Access Token'
		verbose_name_plural = 'API Access Tokens'

	def __str__(self):
		return '%s... (user=%s)' % (self.token[:10], self.user.username)


class ProxySecureSocialAuthorizationServer(SocialAuthorizationServer):
	'''	Proxy model which allows for the social authorization server to appear
		in the same admin group as API and Access Tokens
	'''
	class Meta:
		app_label = 'auth'
		proxy = True
		verbose_name = 'Auth Server'
		verbose_name_plural = 'Authentication Servers'


class ProxyPacsImagingServerGroupAuthorization(PacsImagingServerGroupAuthorization):
	'''	Proxy model which allows for the group imaging permissions to appear in the
		auth admin group.
	'''
	class Meta:
		app_label = 'auth'
		proxy = True
		verbose_name = 'Group Access Permission'
		verbose_name_plural = 'Imaging Server Group Access Permissions'


class SocialAuthorizationServerAdmin(admin.ModelAdmin):
	'''	Django admin structure for manging settings associated with Sonador Social authentication instances.
	'''
	list_display = ('token', 'provider', 'description', 'url_login', 'url_callback', 'default')


class PacsImagingGroupAuthorizationAdmin(admin.ModelAdmin):
	'''	Django admin structure for managing settings associated with Group Access permissions
	'''
	list_display = ('group', 'server', 'resource')
