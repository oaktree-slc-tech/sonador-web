from django.db import models

from django.shortcuts import reverse
from django.utils.html import format_html
from django.contrib import admin

from guru.helpers import gsetting
from guru.helpers.utils.object import pick
from guru.helpers.user import user_displayname

from secure.models import ApiAccess, ApiAccessToken
from secure.admin import ApiAccessAdmin, ApiAccessTokenAdmin
from secure.helpers import masked_value

from ..auth.models import SocialAuthorizationServer, PacsImagingServerUserAuthorization, PacsImagingServerGroupAuthorization, \
	DataService
from ..models import PacsImagingServer, DicomImagingModality, RemoteDICOMwebServer


class SonadorApiAccess(ApiAccess):
	'''	Subclass model which allows for the API access (access ID/secret) to appear in the same model
		as groups and auth servers
	'''
	schema_fields_omit = ('apiaccess_ptr',)
	mask_visible_chars = 5
	mask_ellip = '...'
	mask_sep = '-'

	description = models.CharField(blank=True, null=True, max_length=1024)

	class Meta:
		app_label = 'auth'
		verbose_name = 'API Access'
		verbose_name_plural = 'Access IDs/Secret Keys'
		ordering = ('ctime',)
	
	def __str__(self):
		return '%s... (user=%s)' % (self.access_id[:15], self.user.username)

	@property
	def masked_secret(self):
		return masked_value(self.secret_key, 
			visible_digits=self.mask_visible_chars, sep=self.mask_sep, ellip=self.mask_ellip)

	@property
	def json(self):
		'''	JSON representation of the API access/secret
		'''
		jdata = pick(self, ('access_id', 'description', 'ctime'))
		jdata['secret_key'] = self.masked_secret
		jdata['user'] = { 'id': self.user.pk, 'username': self.user.username, 'name': user_displayname(self.user) }
		return jdata


class SonadorApiAccessToken(ApiAccessToken):
	'''	Subclass model which allows for API access tokens to appear in the same model
		as groups and auth servers.
	'''
	schema_fields_omit = ('apiaccesstoken_ptr',)
	mark_visible_chars = 5
	mask_ellip = '...'
	mask_sep = '-'

	description = models.CharField(blank=True, null=True, max_length=1024)

	class Meta:
		app_label = 'auth'
		verbose_name = 'API Access Token'
		verbose_name_plural = 'API Access Tokens'
		ordering = ('ctime',)

	def __str__(self):
		return '%s... (user=%s)' % (self.token[:10], self.user.username)

	@property
	def masked_token(self):
		return masked_value(self.token,
			visible_digits=self.mark_visible_chars, sep=self.mask_sep, ellip=self.mask_ellip)

	@property
	def json(self):
		'''	JSON representation of the API token
		'''
		jdata = pick(self, (('description', 'ctime')))
		jdata['token'] = self.masked_token
		jdata['user'] = { 'id': self.user.pk, 'username': self.user.username, 'name': user_displayname(self.user) }
		return jdata


class ProxySecureSocialAuthorizationServer(SocialAuthorizationServer):
	'''	Proxy model which allows for the social authorization server to appear
		in the same admin group as API and Access Tokens
	'''
	class Meta:
		app_label = 'auth'
		proxy = True
		verbose_name = 'Auth Server'
		verbose_name_plural = 'Authentication Servers'


class ProxyDataService(DataService):
	'''	Proxy model which allows for data services to appear in the same
		admin group as API and Access Tokens
	'''
	class Meta:
		app_label = 'auth'
		proxy = True
		verbose_name = 'Data Service'
		verbose_name_plural = 'Data Services'


class SocialAuthorizationServerAdmin(admin.ModelAdmin):
	'''	Django admin structure for manging settings associated with Sonador Social authentication instances.
	'''
	list_display = ('token', 'provider', 'description', 'url_login', 'url_callback', 'default')


class DataServiceAdmin(admin.ModelAdmin):
	'''	Django admin structure for managing settings associated with Data Services
	'''
	list_display = ('service_id',  'description', 'active', 'acl_allow_staff',)
	filter_horizontal = ('groups',)

	def service_id(self, obj):
		return obj.pk
	service_id.short_description = 'Service ID'
