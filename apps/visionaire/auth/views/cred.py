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
from secure.helpers import masked_value

from ...admin.auth import SonadorApiAccess, SonadorApiAccessToken
from ...audit import apisettings as audit_api
from ...audit.events import best_effort_audit
from ...views.base import SonadorApiObjectMixin

logger = logging.getLogger(__name__)


class SonadorCredentialAuditMixin(object):
	'''	Audit the issuance and revocation of API access credentials.

		Credential lifecycle is audited for the same reason ACL changes are: a credential is
		a standing grant, so an access trail that cannot be read against the credentials in
		existence at the time is not reviewable.

		As with the ACL views, the hooks are `saveObjectData` and `deleteObject` rather than
		the HTTP verbs. These classes are declarative and inherit their verbs from the
		`guru` and `secure` base classes; `SonadorUserTokenManagementView.delete` is the one
		local exception, and it delegates to the inherited `deleteObject`, so hooking there
		covers the token and credential paths through a single site.

		IMPORTANT -- what is recorded as the resource identifier differs by credential type,
		because for an API token the primary key IS the secret. `BaseApiToken.token` is both
		the pk and the bearer credential ("this value should be kept secret as it can be
		used to access this website with your account"), so it is masked before it reaches
		the record. `BaseApiAccess.access_id` is the public half of an access-id/secret pair
		-- the secret lives in the separate, encrypted `secret_key` -- so it is recorded
		verbatim and stays useful for correlation.
	'''
	def audit_credential_identity(self, instance):
		'''	Resolve the (entity_id, credential_type) pair for a credential instance.

			@returns tuple (entity_id, credential_type)
		'''
		_token = getattr(instance, 'token', None)
		if isinstance(instance, SonadorApiAccessToken) or _token:
			return (masked_value(_token) if _token else None), audit_api.AUDIT_CREDENTIAL_TYPE_TOKEN

		return getattr(instance, 'access_id', None), audit_api.AUDIT_CREDENTIAL_TYPE_ACCESS_KEY

	@best_effort_audit
	def emit_credential_event(self, event_type, instance, request=None):
		'''	Emit an audit event for a credential lifecycle change.

			Both identities are recorded. On the administrative paths -- where one user mints
			or revokes credentials on behalf of another -- the acting user comes from the
			request and the subject from the credential itself, and the two differ. Recording
			only one of them would make an administrative issuance indistinguishable from a
			self-service one.
		'''
		from ...audit.events import emit_audit_event

		_entity_id, _credential_type = self.audit_credential_identity(instance)
		_subject = getattr(instance, 'user', None)

		emit_audit_event(sender=type(self), event_type=event_type,
			user=getattr(request, 'user', None), outcome=True, request=request,
			entity_id=_entity_id, context={
				audit_api.AUDIT_DETAIL_CREDENTIAL_TYPE: _credential_type,
				audit_api.AUDIT_DETAIL_SUBJECT_USER: getattr(_subject, 'username', None) or _subject,
			})

	def saveObjectData(self, request, forminstance, *args, **kwargs):
		'''	Save the credential, then record its issuance.

			Only creation is audited. `saveObjectData` also serves updates, but a credential
			update edits its description -- the credential material itself is `editable=False`
			-- which is not a security event worth a record of its own.
		'''
		_created = not getattr(forminstance.instance, 'pk', None)
		instance = super().saveObjectData(request, forminstance, *args, **kwargs)

		if _created:
			self.emit_credential_event(audit_api.AUDIT_CREDENTIAL_ISSUE,
				instance if instance is not None else forminstance.instance, request=request)

		return instance

	@best_effort_audit
	def capture_credential_audit(self, instance):
		'''	Snapshot what the revocation record needs, BEFORE the row is deleted.

			The subject user is reached through a relation that no longer resolves once the
			credential is gone, so reading it afterwards would produce a record naming
			nobody.
		'''
		_entity_id, _credential_type = self.audit_credential_identity(instance)
		_subject = getattr(instance, 'user', None)

		return {
			'entity_id': _entity_id,
			'context': {
				audit_api.AUDIT_DETAIL_CREDENTIAL_TYPE: _credential_type,
				audit_api.AUDIT_DETAIL_SUBJECT_USER: getattr(_subject, 'username', None) or _subject,
			},
		}

	def audited_credential_delete(self, delete, instance, request=None, *args, **kwargs):
		'''	Run a credential deletion and record it.

			The deletion itself is passed in as a callable rather than reached through
			`super()`, because the two views that delete credentials do not resolve it the
			same way -- see `SonadorUserTokenManagementView.deleteObject`. Routing both
			through here keeps one implementation of the audit behaviour.
		'''
		_snapshot = self.capture_credential_audit(instance)
		result = delete(instance, request=request, *args, **kwargs)

		self.emit_credential_revoke(_snapshot, request=request)
		return result

	@best_effort_audit
	def emit_credential_revoke(self, snapshot, request=None):
		'''	Emit the revocation record from a pre-delete snapshot.

			Guarded, and tolerant of a missing snapshot, so revoking a credential always
			completes. A credential revocation that fails because the audit trail failed
			would leave a live credential in place, which is the opposite of what the
			audit trail exists to protect.
		'''
		from ...audit.events import emit_audit_event

		snapshot = snapshot or {}
		emit_audit_event(sender=type(self), event_type=audit_api.AUDIT_CREDENTIAL_REVOKE,
			user=getattr(request, 'user', None), outcome=True, request=request,
			entity_id=snapshot.get('entity_id'), context=snapshot.get('context'))

	def deleteObject(self, instance, request=None, *args, **kwargs):
		'''	Record the revocation, then remove the credential.
		'''
		return self.audited_credential_delete(
			super().deleteObject, instance, request=request, *args, **kwargs)


class SonadorUserCredentialManagementView(SonadorCredentialAuditMixin, SonadorApiObjectMixin,
		UserCredentialManagementView):
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


class SonadorUserCredentialRestView(SonadorCredentialAuditMixin, SonadorApiObjectMixin, UserCredentialRestView):
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

	def deleteObject(self, instance, request=None, *args, **kwargs):
		'''	Record the token revocation, then remove the token.

			This override exists because `GuruApiObjectUpdateMixin` is mixed in AHEAD of
			`SonadorUserCredentialManagementView` on this class, and it defines its own
			`deleteObject`. That places it earlier in the MRO than the inherited
			`SonadorCredentialAuditMixin.deleteObject`, which is therefore never reached:
			without this, revoking an API token is silently unaudited while revoking an
			access-id/secret pair is recorded normally.

			Re-ordering the bases is not an option -- `SonadorCredentialAuditMixin` already
			sits behind `SonadorUserCredentialManagementView`, so hoisting it in front of
			`GuruApiObjectUpdateMixin` is not a linearizable MRO. Overriding here is, and it
			shares the mixin's implementation rather than restating it.
		'''
		return self.audited_credential_delete(
			super().deleteObject, instance, request=request, *args, **kwargs)


class SonadorAdminUserCredentialsManagementMixin(object):
	'''	Mixin class which provides a getUser method which retrieves the user from a URL 
		parameter rather than from the request. 
	'''
	user_model = get_user_model()
	request_user_fieldname = 'userid'

	def getUser(self, *args, **kwargs):
		'''	Retrieve user instance
		'''
		vkwargs = kwargs.get('vkwargs', {}) or self.kwargs or {}
		return self.user_model.objects.get(pk=vkwargs.get(self.request_user_fieldname))


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