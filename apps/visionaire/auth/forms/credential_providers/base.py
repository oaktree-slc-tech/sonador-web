import abc, six

from guru.errors import AuthError


class ServiceAuthorizationRequest(object):
	'''	Stub object used to mock requests so that user instances can be retrieved from session
		by a service looking to authenticate a user.
	'''
	def __init__(self, session):
		self.session = session


class CredentialValidationError(AuthError):
	'''	Error thrown if a credentials provider is not able to validate a set of credentials.
	'''
	pass


@six.add_metaclass(abc.ABCMeta)
class SonadorCredentialBaseProvider:
	''' Class which provides methods and properties for parsing and working with Sonador credentials 
		issued from different sources.
	'''
	def __init__(self, data):
		self.data = data
		self.token_payload = None
		self.expires_in = None
		self.session = None

	@property
	def user(self):
		return getattr(self, '_user', None)

	@user.setter
	def user(self, val):
		setattr(self, '_user', val)

	@abc.abstractmethod
	def clean(self):
		'''	Decode the credential data and retrieve the user
		'''