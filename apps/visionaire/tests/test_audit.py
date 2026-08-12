'''	Unit tests for the HIPAA audit record builder (sonador#78, AC-17).

	`build_audit_event` is a pure function over plain inputs -- no database, no request
	state, no broker -- so the record shape is verified here without any of that. What the
	live stack is needed for is delivery (AC-4/5/6/13/18), not shape.

	The assertions are deliberately anchored on the wire format rather than on internals:
	DCM codes, the action letter, the outcome code, the timestamp, and the absence of
	credential material are what a downstream audit repository actually consumes, and are
	the things that must not drift silently.
'''
import datetime, json
from unittest import mock

from django.test import SimpleTestCase, override_settings

from ..audit import apisettings as audit_api
from ..audit.events import best_effort_audit
from ..audit.fhir import build_audit_event, resolve_actor, resource_access_type_code
from ..audit.helpers import sanitize_uri
from ..apisettings import SONADOR_USERNAME, SONADOR_USER_PK, SONADOR_USER_LABEL


def detail_map(event):
	'''	Flatten `entity[0].detail` into a plain dict for assertions.
	'''
	entities = event.get('entity') or []
	if not entities:
		return {}

	return {d['type']: d.get('valueString') for d in (entities[0].get('detail') or [])}


class AuditEventCatalogueTests(SimpleTestCase):
	'''	One case per event type in the catalogue (§5.4): DCM codes, action, outcome.
	'''

	def assert_codes(self, event, type_code, subtype_code=None):
		self.assertEqual(event['type']['code'], type_code)
		self.assertEqual(event['type']['system'], audit_api.DCM_SYSTEM)

		if subtype_code is None:
			self.assertNotIn('subtype', event)
		else:
			self.assertEqual(event['subtype'][0]['code'], subtype_code)
			self.assertEqual(event['subtype'][0]['system'], audit_api.DCM_SYSTEM)

	def test_resource_access_read_is_instances_accessed(self):
		event = build_audit_event(audit_api.AUDIT_RESOURCE_ACCESS, user='alice', outcome=True,
			entity_id='1.2.840', context={
				audit_api.AUDIT_DETAIL_METHOD: 'get',
				audit_api.AUDIT_DETAIL_URI: '/dicom-web/studies/1.2.840/series',
				audit_api.AUDIT_DETAIL_DICOM_UID: '1.2.840',
			})

		self.assert_codes(event, '110103')
		self.assertEqual(event['action'], audit_api.AUDIT_ACTION_READ)
		self.assertEqual(event['outcome'], audit_api.AUDIT_OUTCOME_SUCCESS)

	def test_resource_access_cached_matches_uncached_and_flags_the_hit(self):
		'''	A cached grant must be indistinguishable in completeness from an uncached one --
			that is the whole point of FR-4 -- while still being identifiable as a cache hit.
		'''
		context = {
			audit_api.AUDIT_DETAIL_METHOD: 'get',
			audit_api.AUDIT_DETAIL_URI: '/dicom-web/studies/1.2.840/series',
			audit_api.AUDIT_DETAIL_DICOM_UID: '1.2.840',
		}

		uncached = build_audit_event(audit_api.AUDIT_RESOURCE_ACCESS, user='alice',
			outcome=True, entity_id='1.2.840', context=context)
		cached = build_audit_event(audit_api.AUDIT_RESOURCE_ACCESS_CACHED, user='alice',
			outcome=True, entity_id='1.2.840',
			context={**context, audit_api.AUDIT_DETAIL_CACHE_HIT: 'true'})

		self.assertEqual(cached['type'], uncached['type'])
		self.assertEqual(cached['action'], uncached['action'])
		self.assertEqual(cached['outcome'], uncached['outcome'])
		self.assertEqual(cached['agent'][0], uncached['agent'][0])
		self.assertEqual(detail_map(cached).get(audit_api.AUDIT_DETAIL_CACHE_HIT), 'true')
		self.assertNotIn(audit_api.AUDIT_DETAIL_CACHE_HIT, detail_map(uncached))

	def test_user_login(self):
		event = build_audit_event(audit_api.AUDIT_USER_LOGIN, user='alice', outcome=True)
		self.assert_codes(event, '110114', '110122')
		self.assertEqual(event['action'], audit_api.AUDIT_ACTION_EXECUTE)
		self.assertEqual(event['outcome'], audit_api.AUDIT_OUTCOME_SUCCESS)

	def test_user_login_failed_is_a_minor_failure(self):
		event = build_audit_event(audit_api.AUDIT_USER_LOGIN_FAILED, user='alice', outcome=False)
		self.assert_codes(event, '110114', '110122')
		self.assertEqual(event['outcome'], audit_api.AUDIT_OUTCOME_MINOR_FAILURE)

	def test_user_logout(self):
		event = build_audit_event(audit_api.AUDIT_USER_LOGOUT, user='alice', outcome=True)
		self.assert_codes(event, '110114', '110123')
		self.assertEqual(event['action'], audit_api.AUDIT_ACTION_EXECUTE)

	def test_acl_grant_modify_revoke(self):
		for event_type, action in (
				(audit_api.AUDIT_ACL_GRANT, audit_api.AUDIT_ACTION_CREATE),
				(audit_api.AUDIT_ACL_MODIFY, audit_api.AUDIT_ACTION_UPDATE),
				(audit_api.AUDIT_ACL_REVOKE, audit_api.AUDIT_ACTION_DELETE)):

			with self.subTest(event_type=event_type):
				event = build_audit_event(event_type, user='admin', outcome=True, context={
					audit_api.AUDIT_DETAIL_GROUP: 'radiologists',
					audit_api.AUDIT_DETAIL_RESOURCE_SCOPE: '*',
					audit_api.AUDIT_DETAIL_PERMISSIONS: 'view,query',
				})

				self.assert_codes(event, '110113', '110136')
				self.assertEqual(event['action'], action)
				self.assertEqual(detail_map(event)[audit_api.AUDIT_DETAIL_GROUP], 'radiologists')

	def test_credential_issue_and_revoke(self):
		for event_type, action in (
				(audit_api.AUDIT_CREDENTIAL_ISSUE, audit_api.AUDIT_ACTION_CREATE),
				(audit_api.AUDIT_CREDENTIAL_REVOKE, audit_api.AUDIT_ACTION_DELETE)):

			with self.subTest(event_type=event_type):
				event = build_audit_event(event_type, user='admin', outcome=True, context={
					audit_api.AUDIT_DETAIL_SUBJECT_USER: 'alice',
					audit_api.AUDIT_DETAIL_CREDENTIAL_TYPE: audit_api.AUDIT_CREDENTIAL_TYPE_TOKEN,
				})

				self.assert_codes(event, '110114', '110137')
				self.assertEqual(event['action'], action)

				# FR-7: the administrative path mints credentials for someone else, so both
				# identities have to be on the record for it to mean anything.
				self.assertEqual(event['agent'][0]['who']['identifier']['value'], 'admin')
				self.assertEqual(detail_map(event)[audit_api.AUDIT_DETAIL_SUBJECT_USER], 'alice')

	def test_every_catalogued_event_type_builds(self):
		'''	AC-16/AC-17: no event type in the catalogue may fail to serialize.
		'''
		for event_type in audit_api.AUDIT_EVENT_TYPES:
			with self.subTest(event_type=event_type):
				event = build_audit_event(event_type, user='alice', outcome=True,
					context={audit_api.AUDIT_DETAIL_METHOD: 'get'})

				self.assertEqual(event['resourceType'], 'AuditEvent')
				self.assertTrue(event['type']['code'])
				self.assertIn(event['action'], (
					audit_api.AUDIT_ACTION_CREATE, audit_api.AUDIT_ACTION_READ,
					audit_api.AUDIT_ACTION_UPDATE, audit_api.AUDIT_ACTION_DELETE,
					audit_api.AUDIT_ACTION_EXECUTE))


class ResourceAccessTypeCodeTests(SimpleTestCase):
	'''	The §5.5 classification, which decides whether an access reads as a view, a query,
		an export, an import, or a deletion. Evaluation order matters: a delete is a delete
		even when the URI also looks like something else.
	'''

	def test_delete_wins_over_uri_shape(self):
		self.assertEqual(
			resource_access_type_code(method='delete', uri='/dicom-web/studies/1.2/archive'),
			audit_api.DCM_DICOM_STUDY_DELETED)

	def test_archive_is_an_export(self):
		self.assertEqual(
			resource_access_type_code(method='get', uri='/dicom-web/studies/1.2/archive',
				dicom_uid='1.2'),
			audit_api.DCM_EXPORT)

	def test_instances_post_is_an_import(self):
		self.assertEqual(
			resource_access_type_code(method='post', uri='/instances'),
			audit_api.DCM_IMPORT)

	def test_read_without_a_resource_id_is_a_query(self):
		self.assertEqual(
			resource_access_type_code(method='get', uri='/dicom-web/studies'),
			audit_api.DCM_QUERY)

	def test_read_of_a_specific_resource_is_an_access(self):
		self.assertEqual(
			resource_access_type_code(method='get', uri='/dicom-web/studies/1.2/series',
				dicom_uid='1.2'),
			audit_api.DCM_DICOM_INSTANCES_ACCESSED)


class AuditActorTests(SimpleTestCase):
	'''	Actor resolution across the three shapes the authorization form produces, plus the
		cache replay form.
	'''

	def test_internal_superuser_resolves_to_its_configured_identity(self):
		self.assertEqual(resolve_actor(SONADOR_USERNAME), (SONADOR_USERNAME, str(SONADOR_USER_PK)))

	def test_unauthenticated_actor_is_recorded_not_dropped(self):
		'''	AC-5: a denial for an unknown user still needs a populated agent[0].
		'''
		self.assertEqual(resolve_actor(None), (audit_api.AUDIT_ACTOR_UNKNOWN, None))

		event = build_audit_event(audit_api.AUDIT_RESOURCE_ACCESS, user=None, outcome=False,
			context={audit_api.AUDIT_DETAIL_METHOD: 'get'})

		self.assertEqual(event['agent'][0]['who']['identifier']['value'],
			audit_api.AUDIT_ACTOR_UNKNOWN)
		self.assertEqual(event['outcome'], audit_api.AUDIT_OUTCOME_MINOR_FAILURE)

	def test_cached_actor_mapping_preserves_the_primary_key(self):
		self.assertEqual(resolve_actor({'username': 'alice', 'pk': 7}), ('alice', '7'))

	def test_responsible_application_is_recorded_as_a_non_requestor(self):
		event = build_audit_event(audit_api.AUDIT_USER_LOGIN, user='alice')

		self.assertTrue(event['agent'][0]['requestor'])
		self.assertFalse(event['agent'][1]['requestor'])
		self.assertEqual(event['agent'][1]['who']['display'], SONADOR_USER_LABEL)

	def test_client_address_is_recorded_when_a_request_is_available(self):
		class FakeRequest:
			META = {'HTTP_X_FORWARDED_FOR': '10.1.2.3, 192.168.0.1'}

		event = build_audit_event(audit_api.AUDIT_USER_LOGIN, user='alice', request=FakeRequest())
		self.assertEqual(event['agent'][0]['network'], {
			'address': '10.1.2.3', 'type': audit_api.AUDIT_NETWORK_TYPE_IP})

	def test_network_is_omitted_when_no_request_is_available(self):
		event = build_audit_event(audit_api.AUDIT_USER_LOGIN, user='alice')
		self.assertNotIn('network', event['agent'][0])


class AuditRecordedTimestampTests(SimpleTestCase):
	'''	FR-9 / AC-11. The 2024 prototype emitted `datetime.now()` with a `Z` suffix, which
		labels local time as UTC. The distinction is invisible on a UTC host, so it is
		asserted here against an explicit non-UTC instant rather than against "now".
	'''

	def test_recorded_is_timezone_aware_utc(self):
		event = build_audit_event(audit_api.AUDIT_USER_LOGIN, user='alice')
		parsed = datetime.datetime.fromisoformat(event['recorded'])

		self.assertIsNotNone(parsed.tzinfo)
		self.assertEqual(parsed.utcoffset(), datetime.timedelta(0))

	def test_supplied_non_utc_instant_is_converted_not_relabelled(self):
		mountain = datetime.timezone(datetime.timedelta(hours=-6))
		recorded = datetime.datetime(2026, 8, 11, 12, 0, 0, tzinfo=mountain)

		event = build_audit_event(audit_api.AUDIT_USER_LOGIN, user='alice', recorded=recorded)
		parsed = datetime.datetime.fromisoformat(event['recorded'])

		# Same instant, however it is spelled. A relabelled naive timestamp would land six
		# hours off.
		self.assertEqual(parsed, recorded)
		self.assertEqual(parsed.astimezone(datetime.timezone.utc).hour, 18)


class AuditPhiAndSecretTests(SimpleTestCase):
	'''	FR-10 / AC-12. Identifiers are permitted; demographics, tag content, and credential
		values are not.
	'''

	def test_phi_bearing_events_are_labelled_restricted(self):
		event = build_audit_event(audit_api.AUDIT_RESOURCE_ACCESS, user='alice',
			entity_id='1.2.840', context={audit_api.AUDIT_DETAIL_METHOD: 'get'})

		self.assertEqual(event['entity'][0]['securityLabel'][0]['code'],
			audit_api.CONFIDENTIALITY_CODE_RESTRICTED)

	def test_non_phi_events_carry_no_confidentiality_label(self):
		event = build_audit_event(audit_api.AUDIT_USER_LOGIN, user='alice', entity_id='alice')
		self.assertNotIn('securityLabel', event['entity'][0])

	def test_token_value_is_never_serialized(self):
		'''	The emit sites pass `TokenKey` and never `TokenValue`; this guards the record
			builder against a caller that forgets, by asserting on the serialized document
			rather than on any single call site.
		'''
		event = build_audit_event(audit_api.AUDIT_RESOURCE_ACCESS, user='alice',
			entity_id='1.2.840', context={
				audit_api.AUDIT_DETAIL_TOKEN_KEY: 'sonador-api-token',
				audit_api.AUDIT_DETAIL_METHOD: 'get',
			})

		details = detail_map(event)
		self.assertEqual(details[audit_api.AUDIT_DETAIL_TOKEN_KEY], 'sonador-api-token')
		self.assertNotIn('TokenValue', details)

	def test_empty_details_are_dropped_rather_than_serialized_as_null(self):
		event = build_audit_event(audit_api.AUDIT_RESOURCE_ACCESS, user='alice',
			entity_id='1.2.840', context={
				audit_api.AUDIT_DETAIL_METHOD: 'get',
				audit_api.AUDIT_DETAIL_ORTHANC_ID: None,
				audit_api.AUDIT_DETAIL_LEVEL: '',
			})

		details = detail_map(event)
		self.assertIn(audit_api.AUDIT_DETAIL_METHOD, details)
		self.assertNotIn(audit_api.AUDIT_DETAIL_ORTHANC_ID, details)
		self.assertNotIn(audit_api.AUDIT_DETAIL_LEVEL, details)

	def test_non_string_detail_values_are_coerced(self):
		'''	Validity and group ids arrive as integers; FHIR `valueString` is a string.
		'''
		event = build_audit_event(audit_api.AUDIT_RESOURCE_ACCESS, user='alice',
			entity_id='1.2.840', context={
				audit_api.AUDIT_DETAIL_METHOD: 'get',
				audit_api.AUDIT_DETAIL_VALIDITY: 30,
			})

		self.assertEqual(detail_map(event)[audit_api.AUDIT_DETAIL_VALIDITY], '30')


class AuditEventRoundTripTests(SimpleTestCase):
	'''	AC-10: every emitted record must re-parse as a FHIR R4B AuditEvent.
	'''

	def test_records_round_trip_through_the_r4b_model(self):
		import json

		from fhir.resources.R4B.auditevent import AuditEvent

		for event_type in audit_api.AUDIT_EVENT_TYPES:
			with self.subTest(event_type=event_type):
				document = build_audit_event(event_type, user='alice', outcome=True,
					entity_id='1.2.840', context={audit_api.AUDIT_DETAIL_METHOD: 'get'})

				# Through the wire encoding the producer actually uses, not just the dict.
				reparsed = AuditEvent.model_validate(json.loads(json.dumps(document)))
				self.assertEqual(reparsed.type.code, document['type']['code'])

	def test_source_identifies_sonador_as_an_application_server(self):
		event = build_audit_event(audit_api.AUDIT_USER_LOGIN, user='alice')

		self.assertEqual(event['source']['type'][0]['code'],
			audit_api.SECURITY_SOURCE_TYPE_CODE_APPLICATION_SERVER)
		self.assertEqual(event['source']['type'][0]['system'],
			audit_api.SECURITY_SOURCE_TYPE_SYSTEM)
		self.assertTrue(event['source']['observer']['display'])


class AuditUriSanitizationTests(SimpleTestCase):
	'''	FR-10 / AC-12, query strings. A DICOMweb search carries patient demographics as
		ordinary query parameters -- `?PatientName=...&PatientID=...` is a routine QIDO-RS
		request -- so the URI is client-supplied input that can contain PHI. The values are
		dropped at the audit boundary; the parameter names are kept because they are useful
		to a reviewer and are not themselves PHI.
	'''

	SENSITIVE_URI = ('/dicom-web/studies?PatientName=SMITH%5EJOHN&PatientID=MRN-0099887'
		'&AccessionNumber=ACC-42&StudyDate=20260811')

	def test_query_values_never_reach_the_record(self):
		event = build_audit_event(audit_api.AUDIT_RESOURCE_ACCESS, user='alice', outcome=True,
			context={
				audit_api.AUDIT_DETAIL_METHOD: 'get',
				audit_api.AUDIT_DETAIL_URI: self.SENSITIVE_URI,
			})

		serialized = json.dumps(event)
		for value in ('SMITH', 'JOHN', 'MRN-0099887', 'ACC-42', '20260811'):
			with self.subTest(value=value):
				self.assertNotIn(value, serialized)

	def test_path_is_retained(self):
		event = build_audit_event(audit_api.AUDIT_RESOURCE_ACCESS, user='alice', outcome=True,
			context={
				audit_api.AUDIT_DETAIL_METHOD: 'get',
				audit_api.AUDIT_DETAIL_URI: self.SENSITIVE_URI,
			})

		self.assertEqual(detail_map(event)[audit_api.AUDIT_DETAIL_URI], '/dicom-web/studies')

	def test_parameter_names_are_retained(self):
		'''	Knowing a search filtered on PatientID is forensically useful; the value is not
			recorded, so nothing identifying is disclosed.
		'''
		event = build_audit_event(audit_api.AUDIT_RESOURCE_ACCESS, user='alice', outcome=True,
			context={
				audit_api.AUDIT_DETAIL_METHOD: 'get',
				audit_api.AUDIT_DETAIL_URI: self.SENSITIVE_URI,
			})

		self.assertEqual(detail_map(event)[audit_api.AUDIT_DETAIL_QUERY_KEYS],
			'AccessionNumber,PatientID,PatientName,StudyDate')

	def test_sanitization_happens_at_the_boundary_not_only_at_call_sites(self):
		'''	An emit site that forgets to sanitize must still not be able to leak, so the
			builder itself is asserted directly rather than only through a view.
		'''
		path, keys = sanitize_uri(self.SENSITIVE_URI)
		self.assertEqual(path, '/dicom-web/studies')
		self.assertNotIn('MRN-0099887', keys)

	def test_uri_without_a_query_string_is_untouched(self):
		path, keys = sanitize_uri('/dicom-web/studies/1.2.840/series')
		self.assertEqual(path, '/dicom-web/studies/1.2.840/series')
		self.assertIsNone(keys)

	def test_classification_still_works_on_a_sanitized_uri(self):
		'''	The type code is derived from the URI, so sanitizing must not change what the
			event is classified as.
		'''
		event = build_audit_event(audit_api.AUDIT_RESOURCE_ACCESS, user='alice', outcome=True,
			context={
				audit_api.AUDIT_DETAIL_METHOD: 'get',
				audit_api.AUDIT_DETAIL_URI: self.SENSITIVE_URI,
			})

		self.assertEqual(event['type']['code'], '110112')


class AuditFailureIsolationTests(SimpleTestCase):
	'''	FR-11 / AC-13. Emitting is only part of the audit path -- assembling context and
		reading or writing the companion cache entry are audit-only work that runs inside a
		live authorization request. None of it may raise into the request.
	'''

	def test_best_effort_audit_swallows_and_returns_none(self):
		@best_effort_audit
		def explode(self):
			raise RuntimeError('cache backend unreachable')

		with override_settings(AUDIT_LOGGING_ENABLED=True):
			with self.assertLogs('visionaire.audit.events', level='ERROR') as logs:
				self.assertIsNone(explode(None))

		self.assertIn('cache backend unreachable', '\n'.join(logs.output))

	def test_best_effort_audit_is_inert_when_disabled(self):
		calls = []

		@best_effort_audit
		def record(self):
			calls.append(1)
			return 'ran'

		with override_settings(AUDIT_LOGGING_ENABLED=False):
			self.assertIsNone(record(None))

		self.assertEqual(calls, [])

	def test_best_effort_audit_returns_the_value_when_it_works(self):
		@best_effort_audit
		def ok(self):
			return {'detail': 'captured'}

		with override_settings(AUDIT_LOGGING_ENABLED=True):
			self.assertEqual(ok(None), {'detail': 'captured'})

	def test_emit_is_a_no_op_when_disabled(self):
		'''	AC-1: with the switch off nothing is constructed and nothing is sent.
		'''
		from ..audit import events as audit_events

		with override_settings(AUDIT_LOGGING_ENABLED=False):
			with mock.patch.object(audit_events, 'sonador_audit_event') as signal:
				audit_events.emit_audit_event(event_type=audit_api.AUDIT_USER_LOGIN, user='alice')

		signal.send.assert_not_called()

	def test_emit_swallows_a_failing_receiver(self):
		from ..audit import events as audit_events

		with override_settings(AUDIT_LOGGING_ENABLED=True):
			with mock.patch.object(audit_events.sonador_audit_event, 'send',
					side_effect=RuntimeError('receiver blew up')):
				with self.assertLogs('visionaire.audit.events', level='ERROR'):
					audit_events.emit_audit_event(event_type=audit_api.AUDIT_USER_LOGIN, user='alice')

	def test_undelivered_event_is_logged_with_its_payload(self):
		'''	A false return from the producer means the record never reached the broker. The
			event itself is logged so it is recoverable from the application log.
		'''
		from ..audit import events as audit_events
		from ..audit.kafka import SonadorAuditProducer

		with override_settings(AUDIT_LOGGING_ENABLED=True):
			with mock.patch.object(SonadorAuditProducer, 'send', return_value=False):
				with self.assertLogs('visionaire.audit.events', level='ERROR') as logs:
					audit_events.publish_audit_event(None, event_type=audit_api.AUDIT_USER_LOGIN,
						user='alice', outcome=True)

		output = '\n'.join(logs.output)
		self.assertIn('dropped', output)
		self.assertIn('AuditEvent', output)

	def test_producer_send_reports_failure_rather_than_raising(self):
		from ..audit.kafka import SonadorAuditProducer

		with override_settings(AUDIT_LOGGING_ENABLED=True):
			with mock.patch.object(SonadorAuditProducer, 'get_producer', return_value=None):
				self.assertFalse(SonadorAuditProducer.send({'resourceType': 'AuditEvent'}))


class AuditWiringTests(SimpleTestCase):
	'''	The acceptance risk for this feature is wiring, not record shape: an emit site that
		is silently not reached produces an audit log that looks complete and is not. These
		assert the hooks actually resolve, which is a different failure mode from the record
		being built wrongly and is not caught by any builder test.

		This guards a concrete bug found during implementation. `GuruApiObjectUpdateMixin`
		is mixed into `SonadorUserTokenManagementView` AHEAD of its credential base and
		defines its own `deleteObject`, which shadowed the inherited audit hook -- token
		revocation was unaudited while credential revocation was not. Nothing about the
		class body reveals that, and re-ordering the bases is not a linearizable MRO.
	'''

	def resolved_owner(self, cls, method):
		'''	Return the class that actually provides `method` for `cls` under its MRO.
		'''
		for klass in cls.__mro__:
			if method in klass.__dict__:
				return klass.__name__

		return None

	def test_every_acl_and_credential_write_path_resolves_to_an_audit_hook(self):
		from ..auth.views import acl, cred

		auditing = {
			'PacsImagingServerGroupAuthorizationAuditMixin',
			'SonadorCredentialAuditMixin',
			'SonadorUserTokenManagementView',
		}

		views = (
			acl.PacsImagingServerGroupAuthorizationManagementView,
			acl.PacsImagingServerGroupAuthorizationRestView,
			cred.SonadorUserCredentialManagementView,
			cred.SonadorUserCredentialRestView,
			cred.SonadorUserTokenManagementView,
			cred.SonadorAdminUserCredentialManagementView,
			cred.SonadorAdminUserCredentialRestView,
			cred.SonadorAdminUserTokenManagementView,
		)

		for view in views:
			for method in ('saveObjectData', 'deleteObject'):
				with self.subTest(view=view.__name__, method=method):
					owner = self.resolved_owner(view, method)
					self.assertIn(owner, auditing,
						'%s.%s resolves to %s, which does not audit -- the hook is shadowed '
						'and this write path would go unrecorded.' % (view.__name__, method, owner))

	def test_authorization_view_audits_both_the_live_and_cached_paths(self):
		from ..auth.views.service.orthanc_auth import OrthancServiceAuthorizationView

		for hook in ('audit_authorization_response', 'audit_cached_authorization_response',
				'cache_set_audit_context'):
			with self.subTest(hook=hook):
				self.assertTrue(callable(getattr(OrthancServiceAuthorizationView, hook, None)))

	def test_identity_signal_receivers_are_registered(self):
		'''	The receivers connect on import of the signals package from the app's ready(); if
			that import is ever dropped they are written but never called.
		'''
		from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed

		for signal, name in ((user_logged_in, 'user_logged_in'),
				(user_login_failed, 'user_login_failed'), (user_logged_out, 'user_logged_out')):
			with self.subTest(signal=name):
				receivers = [r[1]() if callable(r[1]) else r[1] for r in signal.receivers]
				names = {getattr(r, '__name__', '') for r in receivers if r is not None}
				self.assertTrue(any(n.startswith('audit_') for n in names),
					'no audit receiver connected to %s; identity events would go unrecorded' % name)

	def test_audit_signal_has_a_publishing_receiver(self):
		from ..audit.signals import sonador_audit_event

		self.assertTrue(len(sonador_audit_event.receivers) >= 1)


class AuditConstantReuseTests(SimpleTestCase):
	'''	Guards against the audit package re-declaring values the platform already owns.
		These are equality assertions rather than identity ones because the point is that the
		strings cannot drift apart, whichever module a reader reaches for.
	'''

	def test_token_credential_type_is_the_platform_api_token_name(self):
		from wgtauth.services.apisettings import API_ACCESS_APITOKEN_QSPARAM

		self.assertEqual(audit_api.AUDIT_CREDENTIAL_TYPE_TOKEN, API_ACCESS_APITOKEN_QSPARAM)

	def test_group_detail_is_the_imaging_server_group_resource_name(self):
		from orthancapi import apisettings as orthanc_api

		self.assertEqual(audit_api.AUDIT_DETAIL_GROUP, orthanc_api.IMAGING_SERVER_RESOURCE_GROUP)

	def test_dcm_codes_and_labels_are_addressable_by_name(self):
		'''	The unified tuple stays the record builder's input, but each half is reachable
			without positional indexing.
		'''
		self.assertEqual(audit_api.DCM_QUERY,
			(audit_api.DCMCODE_QUERY, audit_api.DCMLABEL_QUERY))
		self.assertEqual(audit_api.DCMCODE_QUERY, '110112')
		self.assertEqual(audit_api.DCMLABEL_QUERY, 'Query')

	def test_every_unified_code_is_built_from_its_named_halves(self):
		unified = {
			'DICOM_INSTANCES_ACCESSED', 'DICOM_STUDY_DELETED', 'EXPORT', 'IMPORT', 'QUERY',
			'SECURITY_ALERT', 'USER_AUTHENTICATION', 'LOGIN', 'LOGOUT',
			'SECURITY_ROLES_CHANGED', 'USER_SECURITY_ATTRIBUTES_CHANGED',
		}

		for name in unified:
			with self.subTest(code=name):
				self.assertEqual(
					getattr(audit_api, 'DCM_%s' % name),
					(getattr(audit_api, 'DCMCODE_%s' % name), getattr(audit_api, 'DCMLABEL_%s' % name)))


class ImagingServerAuditLabelTests(SimpleTestCase):
	'''	The label belongs to the model, so the live authorization path and the value replayed
		from the response cache cannot render a server differently.
	'''

	def test_named_server_renders_its_name(self):
		from ..models import PacsImagingServer

		self.assertEqual(PacsImagingServer(name='RobOakes-Dev01').auditLabel, 'RobOakes-Dev01')

	def test_unnamed_server_falls_back_to_the_primary_key(self):
		from ..models import PacsImagingServer

		server = PacsImagingServer(name='')
		server.pk = 7
		self.assertEqual(server.auditLabel, '7')

	def test_resolver_passes_through_a_replayed_label(self):
		'''	On a cache hit the emit site holds the rendered string, not the model.
		'''
		from ..audit.helpers import server_audit_label

		self.assertEqual(server_audit_label('RobOakes-Dev01'), 'RobOakes-Dev01')
		self.assertIsNone(server_audit_label(None))

	def test_builder_records_the_model_label(self):
		from ..models import PacsImagingServer

		event = build_audit_event(audit_api.AUDIT_RESOURCE_ACCESS, user='alice',
			server=PacsImagingServer(name='RobOakes-Dev01'),
			context={audit_api.AUDIT_DETAIL_METHOD: 'get'})

		self.assertEqual(detail_map(event)[audit_api.AUDIT_DETAIL_IMAGING_SERVER], 'RobOakes-Dev01')


class AuditUriEdgeCaseTests(SimpleTestCase):
	'''	`sanitize_uri` delegates the scrubbing to `guru.helpers.utils.urls`, whose
		`build_url` requires a netloc or a path. These cover the shapes that would otherwise
		raise inside a record build.
	'''

	def test_query_only_uri_does_not_raise(self):
		self.assertEqual(sanitize_uri('?PatientID=MRN-1'), ('', 'PatientID'))

	def test_fragment_is_stripped(self):
		self.assertEqual(sanitize_uri('/dicom-web/studies#frag'), ('/dicom-web/studies', None))

	def test_empty_query_string_records_no_keys(self):
		self.assertEqual(sanitize_uri('/dicom-web/studies?'), ('/dicom-web/studies', None))

	def test_absolute_uri_is_reduced_to_its_path(self):
		'''	An earlier version of this test asserted that the scheme and host were retained,
			which enshrined a leak: the authority is client-supplied too. See
			`AuditUriAuthorityTests`.
		'''
		self.assertEqual(
			sanitize_uri('http://orthanc:8042/dicom-web/studies?PatientID=MRN-2'),
			('/dicom-web/studies', 'PatientID'))


class AuditUriBypassTests(SimpleTestCase):
	'''	Every position in a DICOMweb URI is client-supplied, and each can carry PHI. These
		cover the three that are not the obvious query-value case, all of which reached the
		record before this was tightened:

		* a path parameter (`;key=value`), which Python's urlparse only recognizes on the
		  final segment, so a mid-path one survived scrubbing entirely;
		* a parameter *name*, since `?SMITH^JOHN=1` puts the name in the key position;
		* a bare path segment, since nothing forces a segment to be an identifier.
	'''

	def assert_clean(self, uri, *forbidden):
		path, keys = sanitize_uri(uri)
		rendered = '%s %s' % (path, keys)

		for value in forbidden:
			with self.subTest(value=value):
				self.assertNotIn(value, rendered)

		return path, keys

	def test_path_parameter_on_the_final_segment_is_stripped(self):
		path, _ = self.assert_clean('/dicom-web/studies;PatientName=SMITH^JOHN', 'SMITH', 'JOHN')
		self.assertEqual(path, '/dicom-web/studies')

	def test_path_parameter_mid_path_is_stripped(self):
		'''	urlparse reports this one inside `path`, not `params`, so it is handled per
			segment rather than relying on the URL helper alone.
		'''
		path, _ = self.assert_clean(
			'/dicom-web/studies;PatientID=MRN-0099887/series', 'MRN-0099887')
		self.assertEqual(path, '/dicom-web/studies/series')

	def test_phi_in_the_parameter_name_is_not_recorded(self):
		_, keys = self.assert_clean('/dicom-web/studies?SMITH^JOHN=1', 'SMITH', 'JOHN')
		self.assertEqual(keys, '+1 unlisted')

	def test_valueless_phi_parameter_is_not_recorded(self):
		_, keys = self.assert_clean('/dicom-web/studies?MRN-0099887', 'MRN-0099887')
		self.assertEqual(keys, '+1 unlisted')

	def test_free_text_path_segment_becomes_a_placeholder(self):
		path, _ = self.assert_clean('/dicom-web/studies/SMITH^JOHN/series', 'SMITH', 'JOHN')
		self.assertEqual(path, '/dicom-web/studies/%s/series' % audit_api.AUDIT_URI_SEGMENT_PLACEHOLDER)

	def test_recognized_keys_are_named_and_unknown_ones_counted(self):
		_, keys = self.assert_clean(
			'/dicom-web/studies?PatientID=X&Bogus^Name=Y&limit=5', 'Bogus', '=X', '=Y')
		self.assertEqual(keys, 'PatientID,limit,+1 unlisted')


class AuditUriRetentionTests(SimpleTestCase):
	'''	The counterpart to the bypass tests: sanitizing must not cost a reviewer the
		information needed to find an event. Identifiers and route tokens survive intact.
	'''

	def test_dicom_uid_is_preserved(self):
		path, _ = sanitize_uri('/dicom-web/studies/1.2.826.0.1.3680043.8.498.104036/series')
		self.assertEqual(path, '/dicom-web/studies/1.2.826.0.1.3680043.8.498.104036/series')

	def test_orthanc_resource_id_is_preserved(self):
		path, _ = sanitize_uri(
			'/dicom-web/studies/2d3cb374-3e51db74-edcf7c1d-2825e6b5-056f0c6a/metadata')
		self.assertEqual(path,
			'/dicom-web/studies/2d3cb374-3e51db74-edcf7c1d-2825e6b5-056f0c6a/metadata')

	def test_numeric_index_is_preserved(self):
		path, _ = sanitize_uri('/dicom-web/studies/1.2.840/series/1.2.9/instances/1.2.3/frames/7')
		self.assertTrue(path.endswith('/frames/7'))

	def test_classification_tokens_survive(self):
		'''	The §5.5 type code is derived from the URI, so the tokens it greps for must not
			be normalized away.
		'''
		for uri, expected in (
				('/tools/find', audit_api.DCMCODE_QUERY),
				('/instances', audit_api.DCMCODE_IMPORT),
				('/dicom-web/studies/1.2.840/archive', audit_api.DCMCODE_EXPORT)):

			with self.subTest(uri=uri):
				path, _ = sanitize_uri(uri)
				method = 'post' if expected == audit_api.DCMCODE_IMPORT else 'get'
				event = build_audit_event(audit_api.AUDIT_RESOURCE_ACCESS, user='alice',
					context={audit_api.AUDIT_DETAIL_METHOD: method,
						audit_api.AUDIT_DETAIL_URI: path,
						audit_api.AUDIT_DETAIL_DICOM_UID: '1.2.840' if 'archive' in uri else None})

				self.assertEqual(event['type']['code'], expected)

	def test_search_keys_remain_useful(self):
		'''	Knowing which attributes a search filtered on is the forensic value being kept.
		'''
		_, keys = sanitize_uri(
			'/dicom-web/studies?PatientName=SMITH^JOHN&PatientID=MRN-1&AccessionNumber=ACC-42')
		self.assertEqual(keys, 'AccessionNumber,PatientID,PatientName')


class AuditUriAuthorityTests(SimpleTestCase):
	'''	The authority is client-supplied like every other part of the URI.
		`OrthancServiceAuthorizationForm.uri` is an unrestricted `CharField`, so an absolute
		URL reaches the audit path even though the authorization plugin sends a path -- and
		the authority can carry a patient identifier in the host, a name in the userinfo, or
		a password in the userinfo.

		The whole authority is therefore discarded rather than sanitized. It carries nothing
		a reviewer needs: the imaging server is recorded separately on `ImagingServer`,
		resolved from the model rather than from the request.
	'''

	def test_host_cannot_carry_an_identifier_into_the_record(self):
		path, _ = sanitize_uri('http://MRN-0099887/dicom-web/studies')
		self.assertEqual(path, '/dicom-web/studies')
		self.assertNotIn('MRN-0099887', path)

	def test_userinfo_name_is_discarded(self):
		path, _ = sanitize_uri('http://SMITH^JOHN@orthanc:8042/dicom-web/studies')
		self.assertEqual(path, '/dicom-web/studies')
		for value in ('SMITH', 'JOHN'):
			with self.subTest(value=value):
				self.assertNotIn(value, path)

	def test_userinfo_password_is_discarded(self):
		'''	Userinfo can carry a credential as well as a name, which FR-10 forbids outright.
		'''
		path, _ = sanitize_uri('http://user:s3cr3t-password@orthanc:8042/dicom-web/studies')
		self.assertEqual(path, '/dicom-web/studies')
		self.assertNotIn('s3cr3t-password', path)

	def test_protocol_relative_authority_is_discarded(self):
		path, _ = sanitize_uri('//MRN-0099887/dicom-web/studies')
		self.assertEqual(path, '/dicom-web/studies')

	def test_authority_never_reaches_a_serialized_record(self):
		'''	Asserted on the built document rather than the helper, so an emit site cannot
			reintroduce it.
		'''
		event = build_audit_event(audit_api.AUDIT_RESOURCE_ACCESS, user='alice', context={
			audit_api.AUDIT_DETAIL_METHOD: 'get',
			audit_api.AUDIT_DETAIL_URI: 'http://MRN-0099887:8042/dicom-web/studies?PatientID=X',
		})

		serialized = json.dumps(event)
		self.assertNotIn('MRN-0099887', serialized)
		self.assertEqual(detail_map(event)[audit_api.AUDIT_DETAIL_URI], '/dicom-web/studies')

	def test_classification_survives_an_absolute_uri(self):
		event = build_audit_event(audit_api.AUDIT_RESOURCE_ACCESS, user='alice', context={
			audit_api.AUDIT_DETAIL_METHOD: 'get',
			audit_api.AUDIT_DETAIL_URI: 'http://orthanc:8042/dicom-web/studies/1.2.840/archive',
			audit_api.AUDIT_DETAIL_DICOM_UID: '1.2.840',
		})

		self.assertEqual(event['type']['code'], audit_api.DCMCODE_EXPORT)
