'''	Sonador API views for working with and managing access credentials
'''
import logging
from django.contrib.auth import get_user_model

from guru import apisettings as gapicodes
from guru.helpers.utils.object import pick
from guru.helpers import operation_results
from guru.forms.helpers import validate_form_data
from guru.errors import OperationError
from guru.views import GuruApiObjectUpdateMixin

from secure.views import UserCredentialManagementView, UserCredentialRestView

from ...admin.auth import SonadorApiAccess, SonadorApiAccessToken
from ...views.base import SonadorApiObjectMixin

logger = logging.getLogger(__name__)


class SonadorUserCredentialManagementView(SonadorApiObjectMixin, UserCredentialManagementView):
	'''	API view which can be used for managing user access credentials in Sonador.
	'''
	def response_object_data(self, instance, *args, **kwarg):
		''' Return full copy of the credentials values. All future API responses will have the 
			credential values masked.
		'''
		return pick(instance, ('access_id', 'secret_key', 'ctime', 'description')) if isinstance(instance, SonadorApiAccess) \
			else pick(instance, ('token', 'ctime', 'description')) if isinstance(instance, SonadorApiAccessToken) \
			else {}

	def response_message(self, instance, success, *args, **kwargs):
		'''	Notify user that the full credential will only be displayed a single time. In the future, 
			sensitive values will be masked.
		'''
		msg = {}
		if success:
			msg[gapicodes.API_MESSAGE] = 'IMPORTANT: Save your credential data in a secure location. ' \
				+ 'Sensitive values will be masked in all future responses.'
		
		return msg


class SonadorUserCredentialRestView(SonadorApiObjectMixin, UserCredentialRestView):
	'''	API view which can be used for managing user access credentials in Sonador.
	'''


class SonadorUserTokenManagementView(GuruApiObjectUpdateMixin, SonadorUserCredentialManagementView):
	'''	API view which can be used for managing token credentials
	'''
	mask_separators = ('-...-', '...', '-')

	def operationCode(self, request, *args, **kwargs):
		if request.method == 'POST':
			return gapicodes.API_OBJECT_CREATE

		return super().operationCode(request, *args, **kwargs)

	def getToken(self, request=None, vargs=None, vkwargs=None):
		''' Retrieve the credential primary key from the request data
		'''
		# Retrieve token value from the request data
		token = self.getRequestJsonData(request=request, vargs=vargs, vkwargs=vkwargs).get(
			self.getModelPrimaryKeyField(request=request, vargs=vargs, vkwargs=vkwargs).name)
		if not token:
			raise self.getDoesNotExist()('Unable to retrieve object instance, invalid credential ID.')

		# Check for a masked token with begins and ends components
		for sep in self.mask_separators:
			if sep in token:
				return token.split(sep)
		
		return token

	def getObject(self, objectid, request=None, vargs=None, vkwargs=None):
		'''	Retrieve a user token: parses the 'token' value from the request JSON body.
		'''
		if isinstance(objectid, (str, int)):
			return super().getObject(objectid, request=request, vargs=vargs, vkwargs=vkwargs)

		elif isinstance(objectid, (tuple, list)):
			if len(objectid) == 2:

				# Retrieve database instance using token fragments
				instance = self.getObjectManager(request=request, vargs=vargs, vkwargs=vkwargs).filter(**{
					'%s__startswith' % self.getModelPrimaryKeyField(request=request, vargs=vargs, vkwargs=vkwargs).name: objectid[0],
					'%s__endswith' % self.getModelPrimaryKeyField(request=request, vargs=vargs, vkwargs=vkwargs).name: objectid[1],
				}).first()

				# Throw 404 if an instance can't be found
				if not instance:
					raise self.getDoesNotExist()('Unable to retrieve object instance, invalid credential ID.')

				return instance

		raise NotImplementedError('Unsupported object ID: %s' % str(objectid))

	def put(self, request, *args, **kwargs):
		'''	Update the user token
		'''
		objectid = self.getToken(request=request, vargs=args, vkwargs=kwargs)
		return super().put(request, objectid, *args, **kwargs)

	def patch(self, request, *args, **kwargs):
		'''	Update the user token (delegates to put)
		'''
		objectid = self.getToken(request=request, vargs=args, vkwargs=kwargs)
		return super().patch(request, objectid, *args, **kwargs)

	def delete(self, request, *args, **kwargs):
		'''	 Implement support for removing the token
		'''
		objectid = self.getToken(request=request, vargs=args, vkwargs=kwargs)
		return super().delete(request, objectid, *args, **kwargs)


class SonadorAdminUserCredentialsManagementMixin(object):
	'''	Mixin class which provides a getUser method which retrieves the user from a URL 
		parameter rather than from the request. 
	'''
	user_model = get_user_model()
	request_user_fieldname = 'userid'

	def getUser(self, *args, **kwargs):
		'''	Retrieve user instance
		'''
		return self.user_model.objects.get(
			pk=(kwargs.get('vkwargs') or {}).get(self.request_user_fieldname))


class SonadorAdminUserCredentialManagementView(
		SonadorAdminUserCredentialsManagementMixin, SonadorUserCredentialManagementView):
	'''	API view which can be used by an admin user for managing user credentials in Sonador.
		User instance is retrieved via a URL parameter rather than from the active request.
	'''


class SonadorAdminUserCredentialRestView(SonadorAdminUserCredentialsManagementMixin, SonadorUserCredentialRestView):
	'''	API REST view which can be used by an admin user to manage user credentials in Sonador.
		User instance is retrieved via a URL parameter rather than from the active request.
	'''


class SonadorAdminUserTokenManagementView(SonadorAdminUserCredentialsManagementMixin, SonadorUserTokenManagementView):
	'''	Admin view which can be used by an admin user for managing token credentials.
		User instance is retrieved via a URL parameter rather than from the active request.
	'''