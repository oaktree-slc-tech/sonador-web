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

	def get_auth_server_or_default(self, request, vargs, vkwargs):
		'''	Retrieve the auth server for the view or the default auth server for Sonador

			@returns tuple:
				1. authserver  (str): primary key for the auth server if a specific instance was requested.
					None if the default server was used.
				2. authserver (model instance) or None: auth server instance (either the requested instance 
					or the default) or None if no authentication servers have been configured
					for the Sonador instance.
		'''
		# Retrieve specific auth server instance
		if self.kwargs.get(self.authserver_objectid_url_param):
			authserver = self.get_auth_server(self.request, self.args, self.kwargs)
			authserver_id = authserver.pk
		
		# Retrieve default auth server instance
		else:
			authserver = get_default_authserver(authserver_model=self.authserver_model)
			authserver_id = None

		return authserver_id, authserver