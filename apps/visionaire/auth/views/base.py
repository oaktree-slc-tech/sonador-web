from ..models import SocialAuthorizationServer


def get_default_authserver(authserver_model=SocialAuthorizationServer):
	'''	Retrieve the default authserver for the platform

		@returns authserver model instance or None (if no default auth server is specified)
	'''
	return authserver_model.objects.first() if authserver_model.objects.count() == 1 \
		else authserver_model.objects.filter(default=True).first()


class OpenIDAuthServerMixin(object):
	'''	View mixin which provdes interfaces required for working with OpenID Authentication Servers
	'''
	authserver_objectid_fieldname = 'pk'
	authserver_objectid_url_param = 'serverid'
	authserver_model = SocialAuthorizationServer

	def get_auth_server(self, request, vargs, vkwargs):
		'''	Retrieve the authorization server. Caches a copy in the view keyword arguments,
			to avoid multiple queries to the database.
		'''
		# Attempt to retrieve auth server from cache
		authserver = vkwargs.get('authserver')

		# Not available from cache, retrieve from the database and place in view keyword arguments
		if not authserver:
			authserver = self.authserver_model.objects.prefetch_related('provider') \
				.get(**{self.authserver_objectid_fieldname : vkwargs.get(self.authserver_objectid_url_param) })
			vkwargs['authserver'] = authserver

		return authserver

