from django.db import models

from django.urls import reverse
from django.contrib import auth

from guru.models import GuruTokenModel

from wgtauth.social.models import SocialAuthorizationBaseServer

from .signals.signals import socialuser_first_login


class SocialAuthorizationServer(SocialAuthorizationBaseServer):
	'''	Sever which implements the OpenID protocol and is able to function
		as an oAuth authentication agent.
	'''
	default = models.BooleanField(default=False, help_text='Use authentication server as default')

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

	def save(self, *args, **kwargs):
		'''	If model instance is marked as "default", clear any previous default
			flags in the database as part of persisting the instance.
		'''
		if self.default:
			type(self).objects.filter(default=True).update(default=False)

		return super(SocialAuthorizationServer, self).save(*args, **kwargs)


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

