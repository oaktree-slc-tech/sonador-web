from django import forms

from guru.filter.forms import GuruFilterForm
from guru.filter.views import GuruQueryParamFilterFormMixin

from orthancapi import apisettings as orthanc_api

from ...audit import apisettings as audit_api
from ...audit import helpers as audit_helpers
from ...audit.events import best_effort_audit
from ...views.dicom import PacsImagingServerChildObjectManagementView, PacsImagingServerChildObjectRestView

from ..models import PacsImagingServerGroupAuthorization
from ..forms.acl import PacsImagingServerGroupAuthorizationForm



class PacsImagingServerGroupAuthorizationFilterForm(GuruFilterForm):
	'''	Filter form which can be used to search for group authorization policy instances
	'''
	group = forms.CharField(max_length=256, required=False)

	filterkey_transforms = {
		'group': 'group__name__icontains',
	}


class PacsImagingServerGroupAuthorizationAuditMixin(object):
	'''	Audit the lifecycle of a group authorization policy.

		A grant is what turns an ACL decision into an access, so a resource-access trail
		that cannot be read alongside the policy changes behind it is not reviewable: a
		reviewer seeing a study access needs to be able to answer what permitted it and who
		granted that.

		The hooks are `saveObjectData` and `deleteObject` rather than `post`/`put`/`delete`.
		These views are almost entirely declarative -- they set `model`, `modelform`, and
		`filterform` and inherit every HTTP verb from the `guru` base classes -- so there is
		no verb here to override. `saveObjectData` is also the point at which the write is
		known to have succeeded, which keeps the trail free of events for changes that were
		rejected downstream.
	'''
	@best_effort_audit
	def audit_policy_context(self, instance):
		'''	Assemble the audit context describing a group authorization policy.

			Records the permissions actually held, not the full field set, so a reviewer
			reads what the grant conferred rather than a wall of false flags. No PHI is
			involved: a policy names a group and a resource pattern, never a patient.
		'''
		return {
			audit_api.AUDIT_DETAIL_IMAGING_SERVER: audit_helpers.server_audit_label(
				getattr(instance, 'server', None)),
			audit_api.AUDIT_DETAIL_GROUP: getattr(getattr(instance, 'group', None), 'name', None),
			audit_api.AUDIT_DETAIL_RESOURCE_SCOPE: getattr(instance, 'resource', None),
			audit_api.AUDIT_DETAIL_PERMISSIONS: ','.join(
				perm for perm in orthanc_api.SONADOR_PERMS if getattr(instance, perm, False)) or 'none',
		}

	@best_effort_audit
	def emit_policy_event(self, event_type, instance, request=None, context=None):
		'''	Emit an audit event for a group authorization policy change.

			Guarded so that a policy write or revocation always completes, whatever the audit
			trail does. The record is what documents the change; it is not what performs it.
		'''
		from ...audit.events import emit_audit_event

		emit_audit_event(sender=type(self), event_type=event_type,
			user=getattr(request, 'user', None), outcome=True, request=request,
			server=getattr(instance, 'server', None),
			entity_id=getattr(instance, 'token', None) or getattr(instance, 'pk', None),
			context=context if context is not None else self.audit_policy_context(instance))

	def saveObjectData(self, request, forminstance, *args, **kwargs):
		'''	Save the policy, then record whether it was created or modified.

			`saveObjectData` serves both create and update, so the two are told apart by
			whether the instance already has a primary key -- read BEFORE the save, because
			after it a newly created row has one too.
		'''
		_created = not getattr(forminstance.instance, 'pk', None)
		instance = super().saveObjectData(request, forminstance, *args, **kwargs)

		self.emit_policy_event(
			audit_api.AUDIT_ACL_GRANT if _created else audit_api.AUDIT_ACL_MODIFY,
			instance if instance is not None else forminstance.instance, request=request)

		return instance

	def deleteObject(self, instance, request=None, *args, **kwargs):
		'''	Record the revocation, then remove the policy.

			The context is captured BEFORE the delete: afterwards the related group and
			server are no longer reachable from a deleted instance, and the record would
			describe nothing. That capture is guarded, so a failure to assemble the context
			costs the record's detail rather than blocking the revocation itself -- refusing
			to revoke access because auditing misbehaved would be the wrong way to fail.
		'''
		_context = self.audit_policy_context(instance)
		_snapshot = self.capture_policy_identity(instance)

		result = super().deleteObject(instance, request=request, *args, **kwargs)

		self.emit_policy_revoke(_snapshot, _context, request=request)
		return result

	@best_effort_audit
	def capture_policy_identity(self, instance):
		'''	Snapshot the server and identifier before the row is deleted.
		'''
		return {
			'server': getattr(instance, 'server', None),
			'entity_id': getattr(instance, 'token', None) or getattr(instance, 'pk', None),
		}

	@best_effort_audit
	def emit_policy_revoke(self, snapshot, context, request=None):
		'''	Emit the revocation record from a pre-delete snapshot.
		'''
		from ...audit.events import emit_audit_event

		snapshot = snapshot or {}
		emit_audit_event(sender=type(self), event_type=audit_api.AUDIT_ACL_REVOKE,
			user=getattr(request, 'user', None), outcome=True, request=request,
			server=snapshot.get('server'), entity_id=snapshot.get('entity_id'), context=context)


class PacsImagingServerGroupAuthorizationManagementView(PacsImagingServerGroupAuthorizationAuditMixin,
		GuruQueryParamFilterFormMixin, PacsImagingServerChildObjectManagementView):
	'''	View class for managing group authorization policies for an imaging server
	'''
	model = PacsImagingServerGroupAuthorization
	modelform = PacsImagingServerGroupAuthorizationForm
	filterform = PacsImagingServerGroupAuthorizationFilterForm

	response_objectid_fieldname = 'token'


class PacsImagingServerGroupAuthorizationRestView(PacsImagingServerGroupAuthorizationAuditMixin,
		PacsImagingServerChildObjectRestView):
	'''	View class for managing specific group authorization policy instances for an imaging server
	'''
	model = PacsImagingServerGroupAuthorization
	modelform = PacsImagingServerGroupAuthorizationForm

	response_objectid_fieldname = 'token'
