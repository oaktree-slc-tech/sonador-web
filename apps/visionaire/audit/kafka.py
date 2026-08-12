'''	Kafka transport for the audit trail.

	The producer sits on the hot path of every DICOM and DICOMweb request, so the
	constraints here are about never making a request wait:

	*	`produce()` is asynchronous -- it enqueues into librdkafka's local buffer and
		returns. Delivery happens on a background thread.
	*	`flush()` blocks until the buffer drains and is therefore called ONLY at process
		shutdown, from an `atexit` hook. Calling it per message (as the 2024 prototype in
		!70 did) turns every authorization into a broker round trip.
	*	`poll(0)` is called after each produce to serve delivery callbacks from prior
		sends. It does not block.
	*	A full local queue raises `BufferError`. The event is logged and dropped; a
		backlog must not become an authorization failure.
'''
import atexit, json, logging, os, threading

from confluent_kafka import Producer

from guru.helpers import gsetting

from .apisettings import AUDIT_FLUSH_TIMEOUT_DEFAULT

logger = logging.getLogger(__name__)


class SonadorAuditProducer:
	'''	Lazily constructed, per-process Kafka producer for audit events.

		`confluent_kafka.Producer` owns background threads which do NOT survive `fork()`.
		Under a multi-worker uvicorn deployment a producer built at import time -- before
		the fork -- is silently broken in every worker: `produce()` accepts the message and
		nothing is ever delivered. The singleton is therefore keyed on the process id and
		rebuilt whenever the pid changes, so each worker constructs its own after forking.
	'''
	_producer = None
	_pid = None
	_lock = threading.Lock()

	@classmethod
	def get_producer(cls):
		'''	Return the producer for the current process, constructing it on first use.

			@returns confluent_kafka.Producer, or None when audit logging is disabled or
				the producer cannot be constructed.
		'''
		if not gsetting('AUDIT_LOGGING_ENABLED'):
			return None

		pid = os.getpid()
		if cls._producer is not None and cls._pid == pid:
			return cls._producer

		with cls._lock:

			# Re-check inside the lock: another thread may have built the producer while
			# this one was waiting for it.
			if cls._producer is not None and cls._pid == pid:
				return cls._producer

			# librdkafka properties are passed through verbatim, so any client property
			# (security.protocol, ssl.*, sasl.*) works without a code change. A copy is
			# taken because ConfigObj hands back a live Section, and librdkafka rejects
			# unknown keys at construction.
			config = dict(gsetting('KAFKA_CONNECTION') or {})
			if not config.get('bootstrap.servers'):
				logger.error('Unable to initialize the Sonador audit producer: no Kafka brokers are '
					+ 'configured. Set "bootstrap.servers" in the [Kafka][[Connection]] section of the site config.')
				return None

			try:
				cls._producer = Producer(config)
				cls._pid = pid

			except Exception as err:
				logger.error('Unable to initialize the Sonador audit producer (pid=%s config=%r): %s'
					% (pid, {k: v for k, v in config.items() if 'password' not in k}, err))
				return None

			logger.info('Sonador audit producer initialized: pid=%s brokers="%s" topic="%s"'
				% (pid, config.get('bootstrap.servers'), gsetting('AUDIT_TOPIC')))

			return cls._producer

	@classmethod
	def delivery_report(cls, err, msg):
		'''	Delivery callback invoked by librdkafka once a message is acknowledged or has
			finally failed.

			A failed delivery is logged and dropped. It is deliberately NOT re-produced:
			librdkafka has already applied its own retry policy by the time this is called,
			so re-producing from the callback is an unbounded, un-backed-off retry loop that
			amplifies a broker outage rather than surviving it. (The Orthanc plugin's
			`SonadorProducer.delivery_report` does exactly that, and additionally raises
			`NameError` on an undefined `kafka_servers` in its own error path.)
		'''
		if err is not None:
			logger.error('Unable to deliver audit event to Kafka: error="%s" payload=%s'
				% (err, msg.value() if msg else None))

	@classmethod
	def send(cls, document):
		'''	Publish a single audit event.

			@input document (dict): the serialized FHIR AuditEvent

			@returns bool: True when the event was enqueued for delivery
		'''
		producer = cls.get_producer()
		if producer is None:
			return False

		topic = gsetting('AUDIT_TOPIC')
		if not topic:
			logger.error('Unable to publish audit event: no audit topic is configured.')
			return False

		try:
			producer.produce(topic, json.dumps(document).encode('utf-8'), callback=cls.delivery_report)

		except BufferError as err:
			# The local queue is full: the broker is unreachable or too slow to keep up.
			# Dropping is the correct trade here -- blocking would push broker latency
			# onto the authorization path.
			logger.error('Unable to queue audit event, the local Kafka buffer is full '
				+ '(outstanding=%s): %s\n%s' % (len(producer), err, document))
			return False

		except Exception as err:
			logger.error('Unable to queue audit event: %s\n%s' % (err, document))
			return False

		# Serve delivery callbacks for previously produced messages. Non-blocking.
		producer.poll(0)
		return True

	@classmethod
	def flush(cls, timeout=None):
		'''	Drain the local queue. Called at process shutdown only -- never from a request.
		'''
		if cls._producer is None or cls._pid != os.getpid():
			return

		try:
			remaining = cls._producer.flush(
				timeout if timeout is not None else AUDIT_FLUSH_TIMEOUT_DEFAULT)

			if remaining:
				logger.error('Sonador audit producer shut down with %s undelivered audit event(s).' % remaining)

		except Exception as err:
			logger.error('Unable to flush the Sonador audit producer at shutdown: %s' % err)


# Drain whatever is still queued when the process exits. Bounded by
# AUDIT_FLUSH_TIMEOUT_DEFAULT so an unreachable broker cannot hang shutdown.
atexit.register(SonadorAuditProducer.flush)
