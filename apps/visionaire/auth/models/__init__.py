import logging, fnmatch, posixpath, copy
from django.db import models

from django.urls import reverse
from django.contrib import auth

from django.db import models
from django.contrib.auth.models import User, Group

from microservices.control import server_controlurl, \
	server_controloperation_put, server_controloperation_delete
from microservices.control.jsonapi import server_controloperation_get

import guru.apisettings as gapicodes
from guru.models import GuruTokenModel
from guru.helpers import site_fullurl
from guru.helpers.compatability import guru_is_safe_url

from wgtauth.apisettings import OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_CODE_RESPONSE_TYPE, \
	OAUTH_CODE_RESPONSE_TYPE

from wgtauth.social.models import SocialAuthorizationBaseServer, OPENID_RESPONSE_TYPE_CODE

from orthancapi import apisettings as orthanc_api

from ...apisettings import SONADOR_PERMS, SONADOR_PERM_QUERY, SONADOR_PERM_UPLOAD, SONADOR_PERM_VIEW, \
	ORTHANC_DICOMWEB_STUDIES, ORTHANC_DICOMWEB_SERIES, ORTHANC_WADO, \
	ORTHANC_CACHE_PATIENT, ORTHANC_CACHE_STUDY, ORTHANC_CACHE_SERIES, \
	ORTHANC_INSTANCES, ORTHANC_TOOLS_FIND, ORTHANC_SYSTEM, ORTHANC_IMAGING_RESOURCES, ORTHANC_QUERY_RESOURCES, ORTHANC_COMMENTS, \
	WILDCARD, ORTHANC_RESOURCE_URL, ORTHANC_RESOURCE_URL_PATIENT, ORTHANC_RESOURCE_URL_STUDY, ORTHANC_RESOURCE_URL_SERIES
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

	# Global permissions
	query = models.BooleanField(default=False, help_text='Submit global DICOM resource queries to the server')
	upload = models.BooleanField(default=False, help_text='Upload DICOM files and attachments to the server')

	# Resource permissions
	resource = models.CharField(max_length=2048, default='*',
		help_text='Resources pattern that the user is authorized to access on the server')
	view = models.BooleanField(default=False, help_text='View images and other resources from the server')	
	modify = models.BooleanField(default=False, help_text='Modify DICOM resources on the server')
	remove = models.BooleanField(default=False, help_text='Remove DICOM resources from the server')
	comment_edit = models.BooleanField(
		verbose_name='Manage Comments', default=False, help_text='Add, edit, or remove resource comments')
	comment_view = models.BooleanField(
		verbose_name='View Comments', default=False, help_text='View resource comments')
	acl = models.BooleanField(
		verbose_name='Access Control', default=False, help_text='View and modify resource access control permissions')

	# Duration of the grant
	duration = models.IntegerField(verbose_name='Grant Duration', default=15, 
		help_text='Time in seconds for which access to the resource should be granted.')

	sep_policiy = ' '
	sep_resource = ','
	
	class Meta:
		app_label = 'visionaire'
		unique_together = ('server', 'group')
		verbose_name = 'Group Permission'
		verbose_name_plural = 'Server Group Permissions'

	def __str__(self, *args, **kwargs):
		return 'Group Authorization: %s for %s (%s:%s)' \
			% (self.group.name, self.server.name, self.server.hostname, self.server.port)
	
	def user_has_perm(self, user, resource, orthanc_id, method, level, dicom_uid=None):
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

			# Server query permission
			if (method.lower() == gapicodes.HTTP_GET.lower() and resource == ORTHANC_DICOMWEB_STUDIES) \
				or (method.lower() == gapicodes.HTTP_POST.lower() and resource in (ORTHANC_CACHE_PATIENT, ORTHANC_CACHE_STUDY, ORTHANC_CACHE_SERIES)) \
				or (method.lower() == gapicodes.HTTP_POST.lower() and resource == ORTHANC_TOOLS_FIND) \
				or (method.lower() == gapicodes.HTTP_GET.lower() and resource == ORTHANC_DICOMWEB_SERIES) \
				or (method.lower() == gapicodes.HTTP_GET.lower() and resource in ORTHANC_QUERY_RESOURCES):
				return self.query

			# Upload permission
			if method.lower() == gapicodes.HTTP_POST.lower() and resource in (ORTHANC_DICOMWEB_STUDIES, ORTHANC_INSTANCES):
				return self.upload

			# Ensure that the requested resource matches a UID within the scope of the user
			elif self.resource == WILDCARD \
				or self.user_has_system_perm(user, level, resource) \
				or self.user_has_resource_perm(user, level, resource, orthanc_id, dicom_uid=dicom_uid):

				# Check system permissions
				if level == ORTHANC_SYSTEM:

					# DICOMweb viewer permissions: view resources or retrieve metadata of specific studie
					if (method.lower() == gapicodes.HTTP_GET.lower() and ORTHANC_DICOMWEB_STUDIES in resource) \
						or (ORTHANC_WADO in resource):

						# Wado-URI or DICOMweb Study/Series Endpoint
						return self.view

					# Check view comment permissions
					elif (ORTHANC_COMMENTS in resource and method.lower() == gapicodes.HTTP_GET.lower()):
						return self.comment_view

					# Check add/edit/remove permissions
					elif (ORTHANC_COMMENTS in resource and method.lower() in (gapicodes.HTTP_POST.lower(), gapicodes.HTTP_PUT.lower(), gapicodes.HTTP_DELETE.lower())):
						return self.comment_edit

				# Check view permissions
				elif level in ORTHANC_IMAGING_RESOURCES and method.lower() == gapicodes.HTTP_GET.lower():
					return self.view

				# Check modify permissions
				elif level in ORTHANC_IMAGING_RESOURCES and method.lower() in (gapicodes.HTTP_POST.lower(), gapicodes.HTTP_PUT.lower()):
					return self.modify

				# Check remove permissions
				elif level in ORTHANC_IMAGING_RESOURCES and method.lower() == gapicodes.HTTP_DELETE.lower():
					return self.remove

		return False
	
	def user_has_system_perm(self, user, level, resource):
		'''	Determine if the user has access to the requested system resource
		'''
		return False

	def user_has_resource_perm(self, user, level, resource, orthanc_id, dicom_uid=None):
		'''	Determine if the user has access to the requested resource
		'''
		# Authorize resource		
		if self.resource == WILDCARD:
			return True

		# Parse resource to grant components
		policy = self.resource_policy()

		# Check resource request against policy components
		for rclass,rgrant in policy.items():
			if orthanc_id in rgrant:
				return True

		# Retrieve authorization scope defined by the policy
		auth_scope = copy.deepcopy(policy)
		for rclass, rgrant in policy.items():
			for uid in rgrant:
				for _rc, _rg in self.resource_authscope(rclass, uid).items():
					if auth_scope.get(_rc): auth_scope[_rc].update(_rg)
					else: auth_scope[_rc] = _rg

		# Check resource request against the authorized scope
		if auth_scope.get(level) and orthanc_id in auth_scope[level]:
			return True

		return False

	def resource_policy(self, resource=None):
		'''	Parse resource policy to components: patient, study, series
		'''
		resource = resource or self.resource
		policy = {}

		for _component in (resource or '').split(self.sep_policiy):

			# Split policy components to resource class and grants
			if '=' in _component:
				_rclass,_rgrant = _component.split('=')
				_rgrant = set(_rgrant.split(self.sep_resource))

				if _rclass in orthanc_api.IMAGING_SERVER_RESOURCES or _rclass.title() in orthanc_api.IMAGING_SERVER_RESOURCES:

					if _rclass.lower() in policy:
						policy[_rclass].update(_rgrant)
					else: policy[_rclass] = _rgrant

		return policy

	def resource_authscope(self, level, orthanc_id, dicom_uid=None):
		'''	Retrieve the UIDs of resources to which the user has access from a resource scope defined in the policy. The auth scope
			is composed of resource types (patient, study, series) and authorized resources/patterns. Building a complete authorization 
			scope also includes inspecting resource permissions for parents/children resources. (Permissions for sibling resources
			are not included in the set of UIDs retrieved by this method.)

			* series: includes UID of study and series within auth scope (sibling series are ommitted and any request will be deined)
			* study: includes UID of patient, all child series are included within auth scope
			* patient: includes UIDs of child studies and series

			@returns dict of UIDs keyed to study level. Values of the dictionary are a set.
		'''
		if not ORTHANC_RESOURCE_URL.get(level.lower()):
			raise ValueError('Unable to create resource authorization scope for level=%s uid=%s. Unsupported resource type.' % (level, uid))

		authscope = {}

		# Retrieve UIDs of parent/child resources
		_r = server_controloperation_get(
			server_controlurl(self.server, posixpath.join(ORTHANC_RESOURCE_URL.get(level.lower()), orthanc_id)), headers=self.server.sonador_auth)		

		# Unpack resource parent UIDs to scope:
		if level.lower() == orthanc_api.IMAGING_SERVER_RESOURCE_SERIES.lower():

			# Study
			s_uid = _r.get(orthanc_api.IMAGING_SERVER_PARENT_STUDY)
			if s_uid:
				authscope[orthanc_api.IMAGING_SERVER_RESOURCE_STUDY.lower()] = set([s_uid])

				# Patient
				_rp = server_controloperation_get(
					server_controlurl(self.server, posixpath.join(ORTHANC_RESOURCE_URL_STUDY, s_uid)), headers=self.server.sonador_auth)
				p_uid = _rp.get(orthanc_api.IMAGING_SERVER_PARENT_PATIENT)
				if p_uid:
					authscope[orthanc_api.IMAGING_SERVER_RESOURCE_PATIENT.lower()] = set([p_uid])
		
		return authscope