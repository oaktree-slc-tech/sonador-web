import logging
from django.db import models

from django.urls import reverse
from django.contrib import auth

from django.db import models
from django.contrib.auth.models import User, Group

import guru.apisettings as gapicodes
from guru.models import GuruTokenModel
from guru.helpers import site_fullurl
from guru.helpers.compatability import guru_is_safe_url

from wgtauth.apisettings import OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_CODE_RESPONSE_TYPE, \
	OAUTH_CODE_RESPONSE_TYPE

from wgtauth.social.models import SocialAuthorizationBaseServer, OPENID_RESPONSE_TYPE_CODE

from ...apisettings import SONADOR_PERMS, SONADOR_PERM_QUERY, SONADOR_PERM_UPLOAD, SONADOR_PERM_VIEW, \
	ORTHANC_DICOMWEB_STUDIES, ORTHANC_DICOMWEB_SERIES, ORTHANC_WADO, \
	ORTHANC_INSTANCES, ORTHANC_TOOLS_FIND, ORTHANC_SYSTEM, ORTHANC_IMAGING_RESOURCES
from .integrations import DataService

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

	def is_safe_url(self, site_resource, allowed_hosts=None):
		'''	Determine if the provided callback URL is safe.
	
			1. Is it part of the Sonador website
				a. Absolute URLs including full domain name for the site
				b. Relative URLs that only include the resource path
			2. Is the redirect URL explicitly included in the url_callback list
				for the authentication server.
		'''
		# Check full resource against Sonador configuration
		usafe = super(SocialAuthorizationServer, self).is_safe_url(
			site_resource, allowed_hosts=allowed_hosts)

		# Complete URLs may cause the is_safe_url from wgtauth to fail.
		# If the fully qualified domain for the site is causing the request to fail,
		# remove the scheme and hostname and check the resource a second time.
		if not usafe:
			usafe = super(SocialAuthorizationServer, self).is_safe_url(
				(site_resource or '').replace(site_fullurl(), ''))

		# If the full URL check and resource check fail, check against the white list
		# for the authentication server.
		return usafe or ((site_resource or '') in (self.callback_url or ''))


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
		from ..signals.signals import socialuser_first_login
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


class PacsImagingServerUserAuthorization(models.Model):
	'''	Permission model which authorizes a user to access the imaging resources of a PACS server.
		TODO: Implement support for user permissions.
	'''
	server = models.ForeignKey('visionaire.PacsImagingServer', on_delete=models.CASCADE, related_name='user_authorizations')
	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='server_authorizations')
	resource = models.CharField(max_length=2048, default='*', 
		help_text='Resources that the user is authorized to access on the server.')
	
	class Meta:
		app_label = 'visionaire'
		unique_together = ('server', 'user')

	def has_perm(self, resource, method, level):
		'''	Check that the user has the permissions required to perfom the action on the provided resource.

			@returns bool: True if the user has the permission, False otherwise
		'''
		return False


class PacsImagingServerGroupAuthorization(models.Model):
	'''	Permission model which authorizes a group to access the imaging resources of a PACS server.
	'''
	server = models.ForeignKey('visionaire.PacsImagingServer', on_delete=models.CASCADE, related_name='group_authorizations')
	group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='server_authorizations')
	resource = models.CharField(max_length=2048, default='*',
		help_text='Resources that the user is authorized to access on the server')

	# Resource permissions
	query = models.BooleanField(default=False, help_text='Submit DICOM resource queries to the server')
	view = models.BooleanField(default=False, help_text='View images and other resources from the server')
	upload = models.BooleanField(default=False, help_text='Upload DICOM files and attachments to the server')
	
	class Meta:
		app_label = 'visionaire'
		unique_together = ('server', 'group')
		verbose_name = 'Group Permission'
		verbose_name_plural = 'Server Group Permissions'

	def __str__(self, *args, **kwargs):
		return 'Group Authorization: %s for %s (%s:%s)' \
			% (self.group.name, self.server.name, self.server.hostname, self.server.port)
	
	def user_has_perm(self, user, resource, orthanc_id, method, level):
		'''	Check that the user has the permissions required to perfom the action on the provided resource.

			@returns bool: True if the user has the permission, False otherwise
		'''
		logger.warning('permission request: user=%s resource="%s" orthanc-id="%s" method="%s" level="%s"' 
			% (user, resource, orthanc_id, method, level))

		# User has superuser permissions
		if user.is_superuser:
			return True
		
		# User is a member of the group
		elif self.group.user_set.filter(username=user.username).exists():

			# Check system permissions
			if level == ORTHANC_SYSTEM:		
				
				# Check query permissions
				if (method.lower() == gapicodes.HTTP_GET.lower() and resource == ORTHANC_DICOMWEB_STUDIES) \
						or (method.lower() == gapicodes.HTTP_POST.lower() and resource == ORTHANC_DICOMWEB_STUDIES) \
						or (method.lower() == gapicodes.HTTP_GET.lower() and resource == ORTHANC_DICOMWEB_SERIES):
					return self.query

				# Check upload permission
				elif method.lower() == gapicodes.HTTP_POST.lower() and resource in (ORTHANC_DICOMWEB_STUDIES, ORTHANC_INSTANCES):
					return self.upload

				# DICOMweb viewer permissions: view resources or retrieve metadata of specific studie
				elif (method.lower() == gapicodes.HTTP_GET.lower() and ORTHANC_DICOMWEB_STUDIES in resource) \
					or (ORTHANC_WADO in resource):

					# Wado-URI or DICOMweb Study/Series Endpoint
					return self.view

			# Check view permissions
			elif level in ORTHANC_IMAGING_RESOURCES:
				return self.view

		return False
