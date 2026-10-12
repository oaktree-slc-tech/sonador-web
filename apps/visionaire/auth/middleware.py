from asgiref.sync import iscoroutinefunction, markcoroutinefunction, sync_to_async

from .origins import registered_client_origins


class RegisteredClientOriginMiddleware:
	'''	Attach the registered client origins to cross-origin requests as
		`request.registered_client_origins`, for the CORS check. The CORS signal is sent from
		synchronous code inside the async middleware chain, where the database cannot be queried,
		so the origins are loaded here. Must be placed before `CorsMiddleware`.
	'''
	sync_capable = True
	async_capable = True

	def __init__(self, get_response):
		self.get_response = get_response
		self.async_mode = iscoroutinefunction(get_response)
		if self.async_mode:
			markcoroutinefunction(self)

	def __call__(self, request):
		if self.async_mode:
			return self.__acall__(request)

		request.registered_client_origins = self.client_origins(request)
		return self.get_response(request)

	async def __acall__(self, request):
		request.registered_client_origins = await sync_to_async(self.client_origins)(request)
		return await self.get_response(request)

	def client_origins(self, request):
		'''	Registered origins, or an empty set for a request that is not cross-origin
		'''
		origin = request.headers.get('Origin')
		if not origin or origin == '%s://%s' % (request.scheme, request.get_host()):
			return frozenset()

		return registered_client_origins()
