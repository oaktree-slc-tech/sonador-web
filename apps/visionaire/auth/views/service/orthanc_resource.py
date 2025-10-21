import logging, posixpath, json

from blake3 import blake3
import orthancapi.apisettings as orthanc_api

from django.core.cache import cache
from guru.helpers import gsetting, create_token

from ...forms.orthanc import OrthancServiceResourceAuthorizationForm

from ..user import user2json
from .orthanc_auth import OrthancServiceAuthorizationView

logger = logging.getLogger(__name__)


class OrthancResourceAclIntrospectionView(OrthancServiceAuthorizationView):
	'''	API view which can be used to introspect resource permissions for a user.
		The view parses all permisions and ACL policies (both global and local)
		and returns a dict indicating the user's permission grants for the 
		provided resource.
	'''
	formclass = OrthancServiceResourceAuthorizationForm
	auth_response_cache_prefix = 'resource-acl'

	def cache_auth_response_key(self, *args, form_data=None, **kwargs):
		'''	Create a auth response cache key for resource ACL introspection requests
		'''
		# Retrieve request components
		form_data = form_data or self.getRequestJsonData(self.request)
		_, orthanc_id, level,_,_,_ = self.get_auth_request_params(form_data=form_data, **kwargs)
		
		if not orthanc_id or not level:
			raise ValueError('Unable to retrieve cache key, invalid Orthanc ID or resource level')

		# Generate hash key
		return self.auth_response_cache_key_template % (
			(gsetting('SECRET_KEY') or create_token()).encode(self.auth_response_encoding),
			('%s%s%s' % (form_data.get('token_key') or create_token(), self.auth_response_cache_sep, 
				form_data.get('token_value') or create_token())).encode(self.auth_response_encoding),
			self.auth_response_cache_prefix.encode(self.auth_response_encoding),
			('%s%s%s' % (level, self.auth_response_cache_sep, orthanc_id)).encode(self.auth_response_encoding))

	def cache_set_authorization_response(self, authorization_response, *args, **kwargs):
		'''	Cache an authorization response from the system cache
		'''
		if authorization_response:

			_cache_key = self.cache_auth_response_key(*args, form_data=self.form.cleaned_data, **kwargs)
			_cache_digest = blake3(_cache_key).hexdigest()
			cache.set(_cache_digest, json.dumps(authorization_response), self.form.expires_in)

			logger.debug('Auth response cached. view="%s" cache-key="%s" digest="%s" response="%s" valid="%s"' % (
				self.auth_response_cache_prefix, _cache_key, _cache_digest, authorization_response, self.form.expires_in
			))

	def get_authorization_response(self, adata, *args, **kwargs):
		'''	Parse the authorization request and create the authorization response
		'''
		user, orthanc_id, level, _, resource, _ = self.get_auth_request_params(
			form_data=self.form.cleaned_data if self.form.is_valid() else self.form.data)

		if self.form.is_valid() and self.form.server.user_has_access(self.form.user):
			user = user or self.form.user
			adata['user'] = user2json(user, include_groups=True, include_permissions=False)

			# Start with a policy set with all permissions set to False
			_perms = dict((_rp, False) for _rp in orthanc_api.SONADOR_RESOURCE_PERMS)

			# Read global policies and determine if any policies for which the user is a member grant
			# permission to the resource.
			for _p in self.form.server.group_authorizations.filter(group__user=user):

				if _p.user_has_resource_access(user, level, resource, orthanc_id):

					# Check all permissions, update "false" permissions with grants from policies
					for _rp in _perms.keys():
						if not _perms.get(_rp) and getattr(_p, _rp, False):
							_perms[_rp] = getattr(_p, _rp, False)

				# If all permissions are true, break iteration
				if all(_v for _v in _perms.values()):
					break

			# Retrieve Orthanc local policies for the resource and add those permissions to the response.
			if not all(_v for _v in _perms.values()):

				# Local permission are querried following global permissions since they require 
				# API requests to be sent to the Orthanc server instance.
				for _p in self.form.server.group_authorizations.filter(group__user=user):

					# Retrieve "local" permissions for the resource from Orthanc
					orthanc_auth = _p.orthanc_resource_auth(
						self.form.user, resource, orthanc_id, self.form.cleaned_data.get('method') or 'get', level)

					# Merge local perissions with global permissions from earlier policy iteration
					for _rp in _perms.keys():
						if not _perms.get(_rp) and orthanc_auth.get(_rp):
							_perms[_rp] = orthanc_auth.get(_rp)

					# Break iteration if all permissions are true
					if all(_v for _v in _perms.values()):
						break
		
			# Add resource permissions to response
			adata['perms'] = _perms
		
		return adata
