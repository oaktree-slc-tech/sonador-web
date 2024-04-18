'''	Credential provider for identiyfiny and authorizing requests for Orthanc hosted static files.
'''
import logging, posixpath
from django.contrib.auth.models import AnonymousUser

from orthancapi.helpers import orthanc_hosted_staticfile

from .base import SonadorCredentialBaseProvider, CredentialValidationError

logger = logging.getLogger(__name__)


class SonadorStaticFileCredentialProvider(SonadorCredentialBaseProvider):
	'''	Credential provider class which can be used to check if a requested resource is an Orthanc
		hosted static file that needs to be authorized for an application to work correctly.

		If the resource is a static file, and a token is not associated with the request, the
		provider class will attach "AnonymousUser" to the request instance.
	'''
	def clean(self):
		'''	Decode the credential data and retrieve the associated user
		'''
		cleaned_data = self.data

		_method = cleaned_data.get('method') or ''
		_resource = cleaned_data.get('uri') or ''
		_,_rtype = posixpath.splitext(_resource)

		# Allow requests for static assets
		if orthanc_hosted_staticfile(uri=_resource, method=_method):

			# Set user for permission credential to AnonymousUser and expiration for five seconds
			self.user = AnonymousUser()
			self.expires_in = 5

			return cleaned_data			

		raise CredentialValidationError('Requested resource uri="%s" method="%s" does not match an Orthanc or Sonador hosted secure static file.'
			% (_resource, _method))