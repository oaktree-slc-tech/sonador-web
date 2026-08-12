'''	Audit event emission.

	`emit_audit_event` is the only entry point an emit site touches. A view calls it with
	plain keyword data; it does not import Kafka, does not construct FHIR objects, and
	does not handle exceptions, because this module owns all three. That keeps audit
	concerns out of the authorization logic and makes each emit site reviewable at a glance.

	The doctrine here is the one already stated by `auth.signals.events.revoke_openid_access_token`:
	a slow or unreachable dependency must never turn a request into an error. Every failure
	in this path -- construction, serialization, or delivery -- is logged at ERROR and
	swallowed. Audit logging never changes an authorization outcome and never produces a 5xx.

	The trade this makes is deliberate and is recorded on sonador#78 as an open policy
	question: v0.1 is fail-open, so a broker outage degrades to local logging rather than
	denying access. Whether a given compliance posture instead requires fail-closed is a
	deployment decision, not an implementation one.
'''
import functools, logging, traceback

from django.dispatch import receiver

from guru.helpers import gsetting

from .signals import sonador_audit_event

logger = logging.getLogger(__name__)


def best_effort_audit(fn):
	'''	Mark a method as audit-only work that must never affect the request it observes.

		Emitting is already best-effort inside `emit_audit_event`, but the work *around* an
		emit is not automatically safe: assembling context reads form state, and the
		authorization response cache reads and writes a companion entry. A cache backend
		that is down, or a companion entry that fails to decode, would otherwise raise
		straight through the authorization path and turn an audit problem into a failed
		request or a 5xx.

		Everything an emit site does purely for the audit trail therefore goes behind this
		decorator: it short-circuits when audit logging is disabled, swallows and logs any
		exception, and returns None so callers can carry on with a missing snapshot rather
		than an exception. Losing an audit record is bad; refusing a legitimate imaging
		request because the audit trail misbehaved is worse, and is what FR-11 forbids.
	'''
	@functools.wraps(fn)
	def _audit_wrapper(*args, **kwargs):

		if not gsetting('AUDIT_LOGGING_ENABLED'):
			return None

		try:
			return fn(*args, **kwargs)

		except Exception as err:
			logger.error('Audit step "%s" failed and was skipped; the request it observes is '
				'unaffected: %s\n%s' % (getattr(fn, '__qualname__', fn), err, traceback.format_exc()))
			return None

	return _audit_wrapper


def emit_audit_event(sender=None, event_type=None, user=None, outcome=True, request=None,
		server=None, entity_id=None, context=None, outcome_desc=None, recorded=None):
	'''	Record an audit event.

		Short-circuits before doing any work when audit logging is disabled, so a
		deployment with the feature off takes no Kafka dependency at runtime and pays
		nothing on the authorization path.

		@input sender (class): the emitting view or module
		@input event_type (str): one of the `apisettings.AUDIT_*` constants
		@input user (User | str | None): the acting identity; `'sonador'` for the internal
			superuser, None for an unauthenticated attempt
		@input outcome (bool): True when granted/succeeded, False when denied/failed
		@input request (HttpRequest, default=None): source of the client address
		@input server (PacsImagingServer, default=None): imaging server context
		@input entity_id (str, default=None): primary resource identifier
		@input context (dict, default=None): event-specific `entity.detail` pairs
		@input outcome_desc (str, default=None)
		@input recorded (datetime, default=None): defaults to `timezone.now()`
	'''
	if not gsetting('AUDIT_LOGGING_ENABLED'):
		return

	try:
		sonador_audit_event.send(sender=sender, event_type=event_type, user=user,
			outcome=outcome, request=request, server=server, entity_id=entity_id,
			context=context, outcome_desc=outcome_desc, recorded=recorded)

	except Exception as err:
		logger.error('Unable to emit audit event "%s": %s\n%s' % (event_type, err, traceback.format_exc()))


@receiver(sonador_audit_event)
def publish_audit_event(sender, event_type=None, user=None, outcome=True, request=None,
		server=None, entity_id=None, context=None, outcome_desc=None, recorded=None, **kwargs):
	'''	Build the FHIR record and publish it to Kafka.

		Imports are deferred into the function body so that neither `fhir.resources` nor
		`confluent_kafka` is imported at module load. A deployment with audit logging
		disabled never reaches this receiver, and nothing outside this package imports
		either library.
	'''
	try:
		from .fhir import build_audit_event
		from .kafka import SonadorAuditProducer

		document = build_audit_event(event_type, user=user, outcome=outcome, request=request,
			server=server, entity_id=entity_id, context=context, outcome_desc=outcome_desc,
			recorded=recorded)

		# A false return means the event was not handed to the broker at all -- the producer
		# could not be constructed, or no topic is configured. The producer logs why; the
		# record itself is logged here so an operator still has the event that was lost
		# rather than only the reason it was lost.
		if not SonadorAuditProducer.send(document):
			logger.error('Audit event "%s" was not queued for delivery and has been dropped: %s'
				% (event_type, document))

	except Exception as err:
		# The serialized event is logged as context so the record is not lost outright when
		# the transport is what failed.
		logger.error('Unable to publish audit event "%s" (user="%s" outcome=%s entity="%s"): %s\n%s'
			% (event_type, user, outcome, entity_id, err, traceback.format_exc()))
