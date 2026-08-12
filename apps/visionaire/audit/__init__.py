'''	HIPAA audit logging for the Sonador web application.

	Every access-control decision and identity event is serialized as a FHIR R4B
	`AuditEvent` and published to a Kafka topic. Kafka is the delivery boundary:
	aggregation, retention, and SIEM integration are decisions made by the entity
	adopting Sonador, not by this package.

	The package is self-contained -- nothing outside it imports `confluent_kafka` or
	`fhir.resources`. Emit sites call `events.emit_audit_event(...)` with plain keyword
	data and nothing else; that helper owns the enable check, the FHIR construction, the
	transport, and the error handling.

	Importing this package is what connects the receiver, so it has to be imported from
	the app's `ready()` (see `visionaire.app.VisionaireAppConfig`). This mirrors
	`visionaire.auth.signals`, whose receivers were once written but never registered
	because nothing imported the package.

	Module layout:

		apisettings.py   event-type constants, DCM code maps, detail key names
		signals.py       the single `sonador_audit_event` signal
		kafka.py         `SonadorAuditProducer` -- lazy, pid-keyed producer singleton
		fhir.py          `build_audit_event(...)` -> dict
		events.py        `emit_audit_event(...)` and the receiver that publishes
'''
from . import events
