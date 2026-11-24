'''	Per-request site resolution.

	Sonador serves several sites (each a `SonadorSite` with its own domain and branding) from one
	deployment. With `SITE_ID` unset, the request host selects the site, and absolute URLs handed
	to a browser are built on that site's configured address, so a user who starts on an
	alternate domain stays on it through authentication and into the viewer. A configured
	`SITE_ID` keeps the single-site behavior: that site, on its own domain, for every request.

	The request host only selects a site. URLs and trust are derived from the configured sites:
	a host which matches no site gets the default site's address and branding, and gains no
	trust of its own.
'''
from django.contrib.sites.models import Site
from django.core.exceptions import ImproperlyConfigured
from django.http.request import split_domain_port

from guru.helpers import gsetting, site_fullurl

from .models.branding import SonadorSite


def pinned_site_id():
	'''	`SITE_ID`, when the deployment fixes every request to one site
	'''
	return gsetting('SITE_ID') or None


def default_site():
	'''	Site used when the request host matches no site: `DEFAULT_SITE_ID`, otherwise the first one
	'''
	site_id = gsetting('DEFAULT_SITE_ID')
	site = Site.objects.filter(pk=site_id).first() if site_id else None
	return site or Site.objects.order_by('pk').first()


def site_for_host(host):
	'''	Site whose domain matches the host, compared with its port first and then without it

		@input host (str): validated request host, `request.get_host()`

		@returns Site or None
	'''
	if not host:
		return None

	return Site.objects.filter(domain__iexact=host).first() \
		or Site.objects.filter(domain__iexact=split_domain_port(host)[0]).first()


def request_site(request=None):
	'''	Site for the request, cached on it. Requests on a host without a site get the default site.

		@returns Site or None (no site configured)
	'''
	if pinned_site_id():
		return Site.objects.filter(pk=pinned_site_id()).first()

	if request is None:
		return default_site()

	if not hasattr(request, '_sonador_site'):
		request._sonador_site = site_for_host(request.get_host()) or default_site()

	return request._sonador_site


def current_site(request=None):
	'''	Branding (`SonadorSite`) of the request's site, or None when it has none
	'''
	site = request_site(request)
	return SonadorSite.objects.filter(pk=site.pk).first() if site else None


def site_netloc(site):
	'''	Public network location of a site: its domain, with `SITE_CONNECT_PORT` added when the
		domain does not name a port of its own
	'''
	port = gsetting('SITE_CONNECT_PORT')
	if port and not split_domain_port(site.domain)[1]:
		return ':'.join((site.domain, port))
	return site.domain


def request_netloc(request=None):
	'''	Network location absolute URLs are built on: the configured address of the request's site
	'''
	site = request_site(request)
	if site is None:
		raise ImproperlyConfigured('No site could be resolved; check SITE_ID and the configured sites.')
	return site_netloc(site)


def site_url(resource_url='', request=None):
	'''	`site_fullurl` built on the address of the request's site (the default site when there is
		no request, the `SITE_ID` site when one is configured)
	'''
	return site_fullurl(resource_url,
		fetch_site_netloc=lambda request=None, _request=request: request_netloc(_request),
		match_site_scheme=gsetting('SITE_CONNECT_MATCH_SITE_SCHEME'),
		match_site_netloc=gsetting('SITE_CONNECT_MATCH_SITE_NETLOC'),
		request=request)


def same_site_hosts():
	'''	Network locations which are Sonador itself: the configured address of every site, and the
		exact entries of `ALLOWED_HOSTS`. A host admitted by an `ALLOWED_HOSTS` wildcard, or on a
		port other than the configured one, is not included.

		@returns set of str: acceptable network locations
	'''
	_hosts = set(gsetting('ALLOWED_HOSTS') or ())
	_hosts.discard('*')
	_hosts.update(site_netloc(site) for site in Site.objects.all())
	return _hosts


class SonadorSiteMiddleware:
	'''	Resolve the site for each request (`request.site`)
	'''

	def __init__(self, get_response):
		self.get_response = get_response

	def __call__(self, request):
		request.site = request_site(request)
		return self.get_response(request)
