'''	Client origins registered with the platform's authorization servers.

	The Callback URL list of each authorization server is the operator's record of which
	endpoints belong to the application. A viewer hosted somewhere other than Sonador is
	authorized by registering its callback there, and that registration covers its origin for
	logout redirects and cross-origin API requests alike.
'''
from six.moves.urllib import parse as urlparse

from .models import SocialAuthorizationServer


def registered_client_origins(authservers=None):
	'''	Origins (scheme, netloc) taken from the Callback URLs registered against the
		authorization servers. Relative and malformed entries are ignored.

		@input authservers (iterable, optional): authorization servers to read; every
			configured server when omitted

		@returns set of tuple: (scheme, netloc) pairs
	'''
	if authservers is None:
		authservers = SocialAuthorizationServer.objects.all()

	origins = set()

	for authserver in authservers:
		for entry in (authserver.callback_url or '').splitlines():
			try: registered = urlparse.urlparse((entry or '').strip())
			except ValueError:
				continue

			if registered.scheme in ('http', 'https') and registered.netloc:
				origins.add((registered.scheme, registered.netloc))

	return origins


def matches_client_origin(url, origins):
	'''	Determine whether `url` is served from one of `origins`.

		A wildcard subdomain entry ("https://*.example.com") covers the subdomains of that domain,
		matching how Django reads a wildcard origin. The bare domain is not covered.

		@input url (str): URL or origin to check
		@input origins (iterable): (scheme, netloc) pairs from `registered_client_origins`

		@returns bool
	'''
	try: requested = urlparse.urlparse(url or '')
	except ValueError:
		return False

	if requested.scheme not in ('http', 'https') or not requested.netloc:
		return False

	for scheme, netloc in origins or ():
		if scheme != requested.scheme:
			continue
		if netloc == requested.netloc:
			return True
		if netloc.startswith('*.') and requested.netloc.endswith(netloc[1:]):
			return True

	return False


def is_registered_client_origin(url, authservers=None):
	'''	Determine whether `url` is served from an origin registered with an authorization server.

		@input url (str): URL or origin to check
		@input authservers (iterable, optional): authorization servers to read; every
			configured server when omitted

		@returns bool
	'''
	return matches_client_origin(url, registered_client_origins(authservers))
