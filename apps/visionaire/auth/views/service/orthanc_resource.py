import orthancapi.apisettings as orthanc_api

from ...forms.orthanc import OrthancServiceResourceAuthorizationForm

from ..user import user2json
from .orthanc_auth import OrthancServiceAuthorizationView


class OrthancResourceAclIntrospectionView(OrthancServiceAuthorizationView):
	'''	API view which can be used to introspect resource permissions for a user.
		The view parses all permisions and ACL policies (both global and local)
		and returns a dict indicating the user's permission grants for the 
		provided resource.
	'''
	formclass = OrthancServiceResourceAuthorizationForm

	def get_authorization_response(self, adata, *args, **kwargs):
		'''	Parse the authorization request and create the authorization response
		'''
		user, orthanc_id, level, _, resource, _ = self.get_auth_request_params()

		if self.form.is_valid() and self.form.server.user_has_access(self.form.user):
			adata['user'] = user2json(self.form.user, include_groups=True, include_permissions=False)

			# Start with a policy set with all permissions set to False
			_perms = dict((_rp, False) for _rp in orthanc_api.SONADOR_RESOURCE_PERMS)

			# Read global policies and determine if any policies for which the user is a member grant
			# permission to the resource.
			for _p in self.form.server.group_authorizations.filter(group__user=self.form.user):

				if _p.user_has_resource_access(self.form.user, level, resource, orthanc_id):

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
				for _p in self.form.server.group_authorizations.filter(group__user=self.form.user):

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
