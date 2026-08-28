import logging, json, fnmatch, posixpath, copy
from django.db import models

from django.urls import reverse
from django.contrib import auth

from django.db import models
from django.contrib.auth.models import User, Group

from microservices.control import server_controlurl, \
	server_controloperation_post, server_controloperation_put, server_controloperation_delete
from microservices.control.jsonapi import server_controloperation_get
from microservices.errors import MicroserviceResourceNotFound

import guru.apisettings as gapicodes
from guru.models import GuruTokenModel
from guru.helpers import site_fullurl
from guru.helpers.compatability import guru_is_safe_url
from guru.helpers.utils.object import pick, omit

from wgtauth.apisettings import OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_CODE_RESPONSE_TYPE, \
	OAUTH_CODE_RESPONSE_TYPE

from wgtauth.social.models import SocialAuthorizationBaseServer, OPENID_RESPONSE_TYPE_CODE

from orthancapi import apisettings as orthanc_api
from orthancapi.auth.acl import ServerAuthorization as OrthancServerAuthorization, \
	ResourceAuthorization as OrthancResourceAuthorization
from orthancapi.auth.validation import SonadorGroup as OrthancSonadorGroup, \
	SonadorUser as OrthancSonadorUser, SonadorResourceAuthorizationRequest

from ...apisettings import SONADOR_PERMS, ORTHANC_DICOMWEB_STUDIES, ORTHANC_DICOMWEB_SERIES, ORTHANC_WADO, \
	ORTHANC_CACHE_PATIENT, ORTHANC_CACHE_STUDY, ORTHANC_CACHE_SERIES, \
	ORTHANC_INSTANCES, ORTHANC_TOOLS_FIND, ORTHANC_SYSTEM, ORTHANC_IMAGING_RESOURCES, ORTHANC_QUERY_RESOURCES, ORTHANC_COMMENTS, \
	WILDCARD, ORTHANC_RESOURCE_URL, ORTHANC_RESOURCE_URL_PATIENT, ORTHANC_RESOURCE_URL_STUDY, ORTHANC_RESOURCE_URL_SERIES

from ..validators import validate_authserver_callback_url
from ..helpers import parse_resource_policy
from .integrations import DataService
from .user import SonadorProxyUser, SonadorProxyGroup

logger = logging.getLogger(__name__)


class SocialAuthorizationServer(SocialAuthorizationBaseServer):
	'''	Sever which implements the OpenID protocol and is able to function
		as an oAuth authentication agent.
	'''
	default = models.BooleanField(default=False, help_text='Use authentication server as default')
	callback_url = models.TextField(blank=True, null=True, verbose_name='Callback URL',
		validators=[validate_authserver_callback_url],
		help_text='Redirect URLs to which the authorization server will forward traffic. Use one '
			+ 'absolute http(s) URI per line. A destination outside this site must match a registered '
			+ 'entry exactly before it receives an issued token: scheme and hostname compare '
			+ 'case-insensitively, an omitted port equals the scheme default (80/443), and the port, '
			+ 'path, and query must otherwise match byte-for-byte. Userinfo, fragments, and entries '
			+ 'declaring a generated response parameter are not permitted, and a single malformed '
			+ 'line rejects the whole registration.')
	enable_idp_token_validation = models.BooleanField(default=False, verbose_name='Validation of IDP Tokens',
		help_text='Enable validation of remote tokens (if supported by the provider).')

	class Meta:
		app_label = 'visionaire'
		verbose_name = 'oAuth2 Auth Credential'
		verbose_name_plural = 'oAuth2 Auth Credentials'

	@property
	def url_login(self):
		'''	Login redirect endpoint (step 1 in oAuth workflow)
		'''
		return reverse('auth:openid-login', args=(self.pk,))

	url_login.fget.short_description = 'Login URL'

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

	def __str__(self):
		return self.description

	def __unicode__(self):
		return self.description


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
		verbose_name = 'Linked oAuth2 User Account'
		verbose_name_plural = 'Linked oAuth2 Accounts'

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


class PacsImagingServerUserAuthorization(GuruTokenModel):
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

	def has_perm(self, *args, **kwargs):
		'''	Check that the user has the permissions required to perfom the action on the provided resource.

			@returns bool: True if the user has the permission, False otherwise
		'''
		return False


class PacsImagingServerGroupAuthorization(GuruTokenModel):
	'''	Permission model which authorizes a group to access the imaging resources of a PACS server.
	'''
	server = models.ForeignKey('visionaire.PacsImagingServer', on_delete=models.CASCADE, related_name='group_authorizations')
	group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='server_authorizations')

	# Server permissions
	query = models.BooleanField(default=False, help_text='Submit global DICOM resource queries to the server')
	upload = models.BooleanField(default=False, help_text='Upload DICOM files and attachments to the server')
	worklist = models.BooleanField(
		verbose_name='Worklist', default=False, help_text='Allow members of the group to create worklist items.')
	tag = models.BooleanField(
		verbose_name='Tags', default=False, help_text='Allow members of the group to view tags.')
	tag_modify = models.BooleanField(
		verbose_name='Manage Tags', default=False, help_text='Allow members of the group to manage tags.')
	devices_list = models.BooleanField(
		verbose_name='Device List', default=False, help_text='Allow members of the group to run distortion filter and device tests.')
	devices_list_modify = models.BooleanField(
		verbose_name='Manage Device List', default=False, help_text='Allow members of the group to manage the device list.')

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

	sep_policy = ' '
	sep_resource = ','
	
	class Meta:
		app_label = 'visionaire'
		unique_together = ('server', 'group')
		verbose_name = 'Group Permission'
		verbose_name_plural = 'Server Group Permissions'

	def __str__(self, *args, **kwargs):
		return 'Group Authorization: %s for %s (%s:%s)' \
			% (self.group.name, self.server.name, self.server.hostname, self.server.port)

	def user_has_perm(self, user, resource, orthanc_id, method, level, dicom_uid=None, action=None):
		'''	Check that the user has the permissions required to perfom the action on the provided resource.

			@returns bool: True if the user has the permission, False otherwise
		'''
		# User has superuser permissions
		if user.is_superuser:
			logger.debug('Superadmin Permission Grant: group=%s resource="%s" level="%s" orthanc_id="%s" dicom_uid="%s"' % (
				self.group.name, resource, level, orthanc_id, dicom_uid,
			))
			return True

		# User is a member of the group, check server permissions
		elif self.group.user_set.filter(username=user.username).exists():
			_server_auth = OrthancServerAuthorization(**pick(self, SONADOR_PERMS))

			# System and scoped resources
			if _acl_scoped_resource := _server_auth.acl_scoped_resource(resource, method) is not None:
				return _acl_scoped_resource

			# Server query permission
			elif _server_auth.query_perm(resource, method) is not None:
				return self.query

			# Upload permission
			elif _server_auth.upload_perm(resource, method) is not None:
				return self.upload

			# Check local permissions for patient, study, series, and instance requests. Integration
			# permissions, such as those associated with group APIs should be processed by the
			# authorization API.
			elif level in orthanc_api.ORTHANC_LOCALAUTH_RESOURCES or level == orthanc_api.ORTHANC_SYSTEM:

				# Retrieve Sonador local permissions
				if _orthanc_auth := self.orthanc_resource_auth(user, resource, orthanc_id, method, level, dicom_uid=dicom_uid):
					
					logger.debug('Orthanc local permissions: user=%s level="%s" orthanc-id="%s" resource="%s" method="%s"\n%s' % (
						user, level, orthanc_id, resource, method, _orthanc_auth,
					))

					if resource and orthanc_api.ORTHANC_DICOMWEB_RESOURCE_ACL in resource \
							and self.query:
						logger.warning(('Orthanc resource-acl request for user=%s level="%s" orthanc-id="%s" resource="%s". Limited grant '
							+ 'because policy includes "query" permission.') % (user, level, orthanc_id, resource))
						return True

					# Parse "local" permisisons from Orthanc and authorize request
					_auth = OrthancResourceAuthorization(**_orthanc_auth, worklist=self.worklist)
					if _auth.resource_perm(resource, orthanc_id, method, level, dicom_uid=dicom_uid, action=action):
						return True

					# Local ACL comment override.
					#
					# When a local ACL defines a CommentView/CommentEdit flag for a resource, that
					# flag is the AUTHORITATIVE decision for comment access to it and must OVERRIDE the
					# global policy: a local comment DENY must not fall through to a global comment
					# grant (and a local grant is already handled by resource_perm above). The rest of
					# this method is additive (local grants supplement the global policy); comments are
					# the one case that also needs to restrict below a global grant, so the override is
					# scoped here to comment actions only and does not change view/modify/remove.
					#
					# Only the leaf resource carries a non-empty `resource`/uri (the plugin's
					# IncludeResourceUri option), so this targets the resource the comment lives on;
					# ancestors are resolved by the `view` traversal in resource_perm. A flag the local
					# ACL never set arrives as None and is intentionally skipped so the request still
					# defers to the global policy.
					#
					# Detect a comment request by EITHER the `action` token OR a comment URI on the
					# leaf resource. The action token is the precise signal, but it is only present
					# when the authorization plugin emits it; the resource-URI fallback keeps the
					# local comment DENY authoritative for the standard `/<type>/<id>/comments` route
					# even when the action token is absent (mirroring the action-independent comment
					# read enforcement in ResourceAuthorization.resource_perm). The check still
					# requires a non-empty leaf `resource`, so non-comment requests are unaffected.
					if resource and (action == orthanc_api.ORTHANC_ACTION_COMMENT \
							or orthanc_api.ORTHANC_COMMENTS in resource):
						if method.lower() == gapicodes.HTTP_GET.lower():
							if _auth.comment_view is not None:
								return _auth.comment_view
						elif _auth.comment_edit is not None:
							return _auth.comment_edit

			# Group API requests
			elif level == orthanc_api.ORTHANC_RESOURCE_GROUP:

				# Tags request
				if orthanc_api.ORTHANC_RESOURCE_TAG in resource and orthanc_id == self.group.pk:

					# Read tags
					if method and method.lower() in (gapicodes.HTTP_GET.lower()):
						return self.tag

					# Change or modify tags
					elif method and method.lower() in (gapicodes.HTTP_POST.lower(), gapicodes.HTTP_PUT.lower()):
						return self.tag_modify

				# Distortion-filter / Devices request
				elif orthanc_api.ORTHANC_RESOURCE_DISTORTION_FILTER_DEVICE in resource and orthanc_id == self.group.pk:

					# Read distortion filter devices
					if method and method.lower() in (gapicodes.HTTP_GET.lower()):
						return self.devices_list

					# Change or modify distortion filter devices
					elif method and method.lower() in (gapicodes.HTTP_POST.lower(), gapicodes.HTTP_PUT.lower(), gapicodes.HTTP_DELETE.lower()):
						return self.devices_list_modify

			# If no other authorization was successful, check if resource UID is within global scope of the user
			#
			# ACL policy-management requests use a DESCEND-ONLY scope (self or descendant of the
			# scoped resource, never an ancestor) -- a series={uid} scope must not authorize policy
			# creation on the parent study (see resource_authscope). This restriction applies only
			# to the LEAF of an acl-management request (a non-empty `resource`, i.e. this call is
			# itself the direct target); an ANCESTOR (empty-resource) traversal call for a
			# DIFFERENT, deeper acl-management leaf must still use the normal ancestor-inclusive
			# scope check below, exactly like modify/remove ancestor calls, or the plugin's
			# all-levels-must-pass rule would deny the whole request.
			if self.resource == WILDCARD \
				or self.user_has_system_perm(user, level, resource) \
				or self.user_has_resource_access(user, level, resource, orthanc_id, dicom_uid=dicom_uid,
					descend_only=bool(resource) and (action == orthanc_api.ORTHANC_ACTION_ACL
						or orthanc_api.ORTHANC_ACL_MANAGEMENT_PATH_REGEX.search(resource))):

				# Check resource request against the policy permissions
				_auth = OrthancResourceAuthorization(**pick(self, SONADOR_PERMS))
				if _auth.resource_perm(resource, orthanc_id, method, level, dicom_uid=dicom_uid, action=action):
					return True

		return False
	
	def user_has_system_perm(self, user, level, resource):
		'''	Determine if the user has access to the requested system resource
		'''
		return False

	def user_has_resource_access(self, user, level, resource, orthanc_id, dicom_uid=None, descend_only=False):
		'''	Determine if the user has access to the requested resource

			`descend_only`, when True, excludes ANCESTOR resources from the authorized scope: a
			scoped policy then authorizes only the resource it names plus its descendants, never
			its parents. Used for ACL policy-management requests (a series={uid} scope must not
			authorize policy creation on the parent study or patient -- see resource_authscope).
			Every other caller leaves this False, preserving the existing ancestor-inclusive
			behavior view/modify/remove/comment rely on to satisfy the auth plugin's
			all-levels-must-pass ancestor traversal.
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
				for _rc, _rg in self.resource_authscope(rclass, uid, descend_only=descend_only).items():
					if auth_scope.get(_rc): auth_scope[_rc].update(_rg)
					else: auth_scope[_rc] = _rg

		# Check resource request against the authorized scope
		if auth_scope.get(level) and orthanc_id in auth_scope[level]:
			return True

		# For series requests which will be authorized by patient policies,
		# retrieve auth scope for each child study of the patient. (This is done since
		# retrieval of child study auth scopes can be resource intensive if there are a lot of studies.
		if level == orthanc_api.IMAGING_SERVER_RESOURCE_SERIES.lower() \
			and policy.get(orthanc_api.IMAGING_SERVER_RESOURCE_PATIENT.lower()):

			for _p in policy.get(orthanc_api.IMAGING_SERVER_RESOURCE_PATIENT.lower()):
				_pr = self.orthanc_resource_info(orthanc_api.IMAGING_SERVER_RESOURCE_PATIENT.lower(), _p)

				for _s in _pr.get('Studies', []):
					_study_authscope = self.resource_authscope(orthanc_api.IMAGING_SERVER_RESOURCE_STUDY, _s, descend_only=descend_only)
					if orthanc_id in _study_authscope.get(orthanc_api.IMAGING_SERVER_RESOURCE_SERIES.lower()):
						return True

		return False

	def orthanc_resource_auth(self, user, resource, orthanc_id, method, level, dicom_uid=None):
		'''	Retrieve the orthanc authorization context for the provided resource request
		'''
		if not isinstance(user, auth.get_user_model()):
			raise ValueError('Unable to retrieve Orthanc local authorization context, invalid user instance')

		# Validation Sonador resource authorization request
		_auth_request = SonadorResourceAuthorizationRequest(
			user=OrthancSonadorUser(id=user.pk, **pick(user, ('username', 'email'))),
			group=OrthancSonadorGroup(id=self.group.pk, name=self.group.name),
			level=level, method=method, uri=resource, **{ 'orthanc-id': orthanc_id, 'dicom-uid': dicom_uid })
		_rdata = json.loads(_auth_request.json())

		# Ensure that keys contain a dash instead of an underscore
		for f in ('orthanc_id', 'dicom_uid'):
			_val = _rdata.pop(f, None)
			
			# Replace keyname with dash
			if _val is not None:			
				_rdata[f.replace('_', '-')] = _val		

		_acl_rdata = server_controloperation_post(self.server, _rdata, resource='system/acl/resource', 
			headers=self.server.sonador_auth)
		logger.debug('<---  Sonador -> Orthanc Resource Authorization Request/Response group="%s" group-name="%s" level="%s"  --->\nrequest: %s\nresponse: %s\n<--- --->' % (
			self.group.pk, self.group.name, level, _rdata, _acl_rdata
		))
		return _acl_rdata

	def orthanc_resource_info(self, level, orthanc_id):
		'''	Retrieve the resource details for the provided Orthanc ID

			A resource which is no longer present on the imaging server degrades to an empty
			result rather than propagating the error. The resource policy stores Orthanc IDs as
			text (`study={id} series={id}`) and nothing prunes them when a resource is removed,
			so a stale UID is an expected condition; letting the 404 escape would make removing
			one study break authorization for every OTHER resource sharing the same group
			policy, since resource_authscope walks every UID in the policy.

			@returns JSON (dict) with resource details from Orthanc API, or an empty dict when
				the resource no longer exists
		'''
		if not ORTHANC_RESOURCE_URL.get(level.lower()):
			raise ValueError('Unable to create resource authorization scope for level=%s uid=%s. Unsupported resource type.' % (level, orthanc_id))

		try:
			return server_controloperation_get(
				server_controlurl(self.server, posixpath.join(ORTHANC_RESOURCE_URL.get(level.lower()), orthanc_id)),
				headers=self.server.sonador_auth)

		except MicroserviceResourceNotFound:
			logger.info('Resource level=%s uid=%s referenced by policy=%s is no longer present on server=%s. '
				'Treating as outside the authorization scope.' % (level, orthanc_id, self.pk, self.server.pk))
			return {}

	def resource_policy(self, resource=None):
		'''	Parse resource policy to components: patient, study, series
		'''
		return parse_resource_policy(
			resource or self.resource, sep_policy=self.sep_policy, sep_resource=self.sep_resource)

	def resource_authscope(self, level, orthanc_id, dicom_uid=None, descend_only=False):
		'''	Retrieve the UIDs of resources to which the user has access from a resource scope defined in the policy. The auth scope
			is composed of resource types (patient, study, series) and authorized resources/patterns. Building a complete authorization
			scope also includes inspecting resource permissions for parents/children resources. (Permissions for sibling resources
			are not included in the set of UIDs retrieved by this method.)

			* series: includes UID of study and series within auth scope (sibling series are ommitted and any request will be deined)
			* study: includes UID of patient and child series
			* patient: includes UIDs of child studies

			`descend_only`, when True, omits ANCESTOR UIDs from the returned scope (the parent
			study/patient of a series, or the parent patient of a study), leaving only the
			resource's own descendants. Used for ACL policy-management requests, where a scoped
			grant must not authorize managing policies on a resource's ancestors (a series scope
			must not reach its parent study) -- see the docstring on user_has_resource_access.

			@returns dict of UIDs keyed to study level. Values of the dictionary are a set.
		'''
		authscope = {}

		# Retrieve details of authorized resource
		_r = self.orthanc_resource_info(level, orthanc_id)

		# Series related UIDs: parent study and patient (omitted when descend_only, since a
		# series has no descendants of its own -- a descend-only series scope authorizes
		# nothing beyond the series itself, which the direct-match check already covers)
		if level.lower() == orthanc_api.IMAGING_SERVER_RESOURCE_SERIES.lower() and not descend_only:

			# Study
			s_uid = _r.get(orthanc_api.IMAGING_SERVER_PARENT_STUDY)
			if s_uid:
				authscope[orthanc_api.IMAGING_SERVER_RESOURCE_STUDY.lower()] = set([s_uid])

				# Patient. Routed through orthanc_resource_info so a study which has since been
				# removed degrades to "no parent patient" instead of raising.
				_rp = self.orthanc_resource_info(orthanc_api.IMAGING_SERVER_RESOURCE_STUDY, s_uid)
				p_uid = _rp.get(orthanc_api.IMAGING_SERVER_PARENT_PATIENT)
				if p_uid:
					authscope[orthanc_api.IMAGING_SERVER_RESOURCE_PATIENT.lower()] = set([p_uid])

		# Study related UIDs: parent patient (omitted when descend_only) and child series
		elif level.lower() == orthanc_api.IMAGING_SERVER_RESOURCE_STUDY.lower():

			# Patient
			if not descend_only:
				p_uid = _r.get(orthanc_api.IMAGING_SERVER_PARENT_PATIENT)
				if p_uid:
					authscope[orthanc_api.IMAGING_SERVER_RESOURCE_PATIENT.lower()] = set([p_uid])

			# Child series
			sx_uid = _r.get(orthanc_api.IMAGING_SERVER_RESOURCE_SERIES, [])
			if sx_uid:
				authscope[orthanc_api.IMAGING_SERVER_RESOURCE_SERIES.lower()] = set(sx_uid)

		# Patient related UIDs: authorize access to child studies
		elif level.lower() == orthanc_api.IMAGING_SERVER_RESOURCE_PATIENT.lower():

			# Child studies
			s_uid = _r.get('Studies', [])
			if s_uid:
				authscope[orthanc_api.IMAGING_SERVER_RESOURCE_STUDY.lower()] = set(s_uid)
		
		return authscope

	@property
	def json(self):
		_json = {
			'token': self.pk, 'server': self.server.pk, 'group': self.group.pk,
			**pick(self, ('query', 'upload', 'tag', 'tag_modify', 'devices_list', 'devices_list_modify',
				'resource', 'view', 'remove', 'comment_view', 'comment_edit', 'acl', 'duration', 'worklist'))
		}
		return _json