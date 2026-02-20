from django.db import models
from django import forms

from django.shortcuts import reverse
from django.utils.html import format_html
from django.contrib import admin

from guru.helpers import gsetting
from guru.helpers.utils.object import pick
from guru.helpers.user import user_displayname

from secure.models import ApiAccess, ApiAccessToken
from secure.admin import ApiAccessAdmin, ApiAccessTokenAdmin
from secure.helpers import masked_value

from core.forms import SonadorBaseForm

from ..auth.models import SocialAuthorizationServer, PacsImagingServerUserAuthorization, PacsImagingServerGroupAuthorization, \
	DataService
from ..models import PacsImagingServer, DicomImagingModality, RemoteDICOMwebServer
from ..auth.views.base import get_default_authserver


# cred: Credential Management

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


# idp: oAuth2/OIDC Identity Provider (IdP) Management

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

	def __str__(self):
		return self.description

	def __unicode__(self):
		return self.description


class SocialAuthorizationServerForm(SonadorBaseForm):
	''' Form instance providing validation of Sonador authorization server instances
	'''
	class Meta:
		model = ProxySecureSocialAuthorizationServer
		fields = '__all__'

	def clean(self, *args, **kwargs):
		'''	Ensure that IdP provider instances with IdP token validation enabled are associated
			with a provider which provides a `validate_token` method.
		'''
		cleaned_data = super().clean(*args, **kwargs)

		# Ensure that IdP token provider supports remote token validation
		if cleaned_data.get('enable_idp_token_validation') and not cleaned_data.get('provider').validate_token:
			raise forms.ValidationError({
					'enable_idp_token_validation': [
						"Remote IdP token validation requires a provider with a `validate_token` method.",
						'Provider "%s" does not support remote token validation' % cleaned_data.get('provider').name,
					]
				})


		return cleaned_data


class SocialAuthorizationServerAdmin(admin.ModelAdmin):
	'''	Django admin structure for manging settings associated with Sonador Social authentication instances.
	'''
	list_display = ('server_id', 'provider', 'description', 'default', 'enable_idp_token_validation', 'url_login', 'url_callback',)
	form = SocialAuthorizationServerForm
	search_fields = ('description',)

	@admin.display(description='Server ID')
	def server_id(self, obj):
		return obj.pk


class SocialAuthorizationServerSearchAdmin(admin.ModelAdmin):
	'''	Django admin structure for enabling search on SocialAuthorizationServer instances
	'''
	search_fields = ('description', 'provider__description')

	def has_module_permission(self, request): return False


# integrations: Data Services


class DataServiceForm(SonadorBaseForm):
	'''	Form instance provid9ing validation of Sonador Data services
	'''
	class Meta:
		
		fields = '__all__'
		exclude = ('token',)

	def clean(self, *args, **kwargs):
		'''	Ensure that requried components for OIDC are enabled.
			1. Auth server must be defined for the service or deployment.
			2. Callback URLs are included.
		'''
		cleaned_data = super().clean(*args, **kwargs)

		# If OIDC is enabled, make sure that an authserver and callback URLs are included.
		if cleaned_data.get('openid_allow_auth'):

			# Check for the presence of an auth server (either explicitly defined or the default for the deployment)
			_authserver = cleaned_data.get('authserver') or get_default_authserver(ProxySecureSocialAuthorizationServer)
			if not _authserver:
				raise forms.ValidationError({
					'openid_allow_auth': [
						'OpenID Connect Authorization requires an authorization server be defined for the Sonador deployment.',
					],
					'authserver': ['No authorization server selected or default server defined for the deployment'],
				})

			# Ensure that redirect URLs have been populated
			if not cleaned_data.get('openid_callback_url'):
				raise forms.ValidationError({
					'openid_callback_url': ['Please specify authorized callback URLs for the data service'],
				})

		return cleaned_data


class DataServiceAdmin(admin.ModelAdmin):
	'''	Django admin structure for managing settings associated with Data Services
	'''
	list_display = ('service_id',  'description', 'active', 'acl_allow_staff', 'oidc_auth_enabled',
		'oidc_login_url', 'oidc_callback_url')
	list_filter = ('active', 'openid_allow_auth')
	readonly_fields = ('openid_client_id',)
	form = DataServiceForm
	filter_horizontal = ('groups',)
	autocomplete_fields = ('authserver',)

	@admin.display(description='Service ID')
	def service_id(self, obj):
		return obj.pk

	@admin.display(description='OIDC Auth Enabled', boolean=True)
	def oidc_auth_enabled(self, obj):
		return obj.openid_allow_auth

	@admin.display(description='OpenID Login URL')
	def oidc_login_url(self, obj):
		return obj.url_login

	@admin.display(description='OpenID Callback URL')
	def oidc_callback_url(self, obj):
		return obj.url_callback