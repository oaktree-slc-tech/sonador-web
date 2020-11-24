import logging
from django.db import models

from django.urls import reverse
from django.contrib import auth

from guru.models import GuruTokenModel
from guru.helpers import site_fullurl
from guru.helpers.compatability import guru_is_safe_url

from wgtauth.apisettings import OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_CODE_RESPONSE_TYPE, \
	OAUTH_CODE_RESPONSE_TYPE

from wgtauth.social.models import SocialAuthorizationBaseServer, OPENID_RESPONSE_TYPE_CODE

from .signals.signals import socialuser_first_login

logger = logging.getLogger(__name__)


class SocialAuthorizationServer(SocialAuthorizationBaseServer):
	'''	Sever which implements the OpenID protocol and is able to function
		as an oAuth authentication agent.
	'''
	default = models.BooleanField(default=False, help_text='Use authentication server as default')
	callback_url = models.TextField(blank=True, null=True, verbose_name='Callback URL',
		help_text='Redirect URLs to which the authorization server will forward traffic. Use one line per URI.')

	class Meta:
		app_label = 'visionaire'
		verbose_name = 'Social Auth Credential'
		verbose_name_plural = 'Social Auth Server Credentials'

	@property
	def url_login(self):
		'''	Login redirect endpoint (step 1 in oAuth workflow)
		'''
		return reverse('auth:openid-login', args=(self.pk,))

	@property
	def url_callback(self):
		'''	Login callback endpoint (step 2 in oAuth workflow)
		'''
		return reverse('auth:openid-login-callback', args=(self.pk,))

	url_callback.fget.short_description = 'OpenID Callback URL'

	@property
	def url_token(self):
		'''	Server specific token grant URL
		'''
		return reverse('auth:openid-auth-token', args=(self.pk,))

	def save(self, *args, **kwargs):
		'''	If model instance is marked as "default", clear any previous default
			flags in the database as part of persisting the instance.
		'''
		if self.default:
			type(self).objects.filter(default=True).update(default=False)

		return super(SocialAuthorizationServer, self).save(*args, **kwargs)

	def is_safe_url(self, site_resource):
		'''	Determine if the provided callback URL is safe.
	
			1. Is it part of the Sonador website
				a. Absolute URLs including full domain name for the site
				b. Relative URLs that only include the resource path
			2. Is the redirect URL explicitly included in the url_callback list
				for the authentication server.
		'''
		# Check full resource against Sonador configuration
		usafe = super(SocialAuthorizationServer, self).is_safe_url(site_resource)

		# Complete URLs may cause the is_safe_url from wgtauth to fail.
		# If the fully qualified domain for the site is causing the request to fail,
		# remove the scheme and hostname and check the resource a second time.
		if not usafe:
			usafe = super(SocialAuthorizationServer, self).is_safe_url(
				site_resource.replace(site_fullurl(), ''))

		# If the full URL check and resource check fail, check against the white list
		# for the authentication server.
		return usafe or site_resource in (self.callback_url or '')


class SocialUserAccount(GuruTokenModel):
	'''	Model used to link social authorization providers to specific user instances
	'''
	social_provider = models.ForeignKey(SocialAuthorizationServer,
		verbose_name='Social Auth Provider', related_name='social_user_profiles',
		on_delete=models.CASCADE)
	user = models.ForeignKey(auth.get_user_model(),
		verbose_name='User', related_name='social_user_profiles',
		on_delete=models.CASCADE)
	social_user_id = models.CharField(max_length=128, verbose_name='Social User ID',
		help_text='User ID retrieved from the Social Auth Provider')
	email = models.EmailField(max_length=512, verbose_name='Social Account Email',
		blank=True, null=True, help_text='Email account associated with the social user')

	class Meta:
		unique_together = ('social_provider', 'social_user_id', 'user')
		app_label = 'visionaire'
		verbose_name = 'Linked Social User Account'
		verbose_name_plural = 'Linked Social Auth Accounts'

	def signal_first_login(self, request, registration=False):
		'''	Trigger the socialuser_first_login signal for the model instance

			@input registration (bool, default=False): Indicates whether the social media profile is
				associated with a new account.
		'''
		socialuser_first_login.send(
			sender=type(self), social_profile=self, request=request, registration=registration)

	@property
	def json(self):
		return {
			'social_provider': self.social_provider.pk,
			'user': self.user.pk,
			'social_user_id': self.social_user_id,
			'email': self.email
		}

