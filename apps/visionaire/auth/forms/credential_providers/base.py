from wgtauth.services.credential_providers.base import DataServiceCredentialBaseProvider, \
	ServiceAuthorizationRequest, CredentialValidationError



class SonadorCredentialBaseProvider(DataServiceCredentialBaseProvider):
	''' Class which provides methods and properties for parsing and working with Sonador credentials 
		issued from different sources.
	'''