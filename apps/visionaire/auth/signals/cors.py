from django.dispatch import receiver

from corsheaders.signals import check_request_enabled

from ..origins import matches_client_origin


@receiver(check_request_enabled)
def allow_registered_client_origins(sender, request, **kwargs):
	'''	Accept cross-origin requests from origins registered as authorization server callbacks.
		Consulted only for origins the CORS settings do not already allow; the origins are
		loaded by `RegisteredClientOriginMiddleware`.
	'''
	return matches_client_origin(request.headers.get('Origin'),
		getattr(request, 'registered_client_origins', None))
