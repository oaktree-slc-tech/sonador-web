'''	Unit tests for Data Service OAuth registered-redirect enforcement.

	`openid_callback_url` is enforced as a set of registered redirect URIs, one per line.
	These tests pin the matcher in `wgtauth.services.redirects` and the flow enforcement in
	the concrete Sonador views: `redirect_uri` must exactly match a registered entry, a
	"next" landing target must be an exact entry or on a registered origin, validation
	fails closed and runs before an authorization code is issued, and missing configuration
	is a 403 rather than a 500.
'''
import logging, time

from contextlib import contextmanager
from unittest import mock
from urllib.parse import urlsplit, parse_qs

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from wgtauth.services.transactions import TRANSACTION_MAX_AGE
from wgtauth.services.redirects import is_registered_redirect_uri, is_valid_continuation, \
	append_response_parameters, parse_redirect_uri, validate_redirect_uri_configuration
from django.core.exceptions import ValidationError

from ..auth.models import DataService, SocialAuthorizationServer
from . import fixtures


REGISTERED = 'https://viewer.example.com:8443/oauth/callback'


@contextmanager
def capture_logs(level=logging.DEBUG):
	'''	Capture everything written to the root logger, including tracebacks, and return a
		callable yielding it as one string. Unlike `assertLogs` this tolerates a block which
		logs nothing, which is the expected result for the paths asserted on here.
	'''
	records = []

	class _Capture(logging.Handler):
		def emit(self, record):
			records.append(self.format(record))

	handler = _Capture()
	handler.setFormatter(logging.Formatter('%(message)s'))

	root = logging.getLogger()
	previous_level, previous_disable = root.level, logging.root.manager.disable

	logging.disable(logging.NOTSET)
	root.addHandler(handler)
	root.setLevel(level)

	try: yield lambda: '\n'.join(records)
	finally:
		root.removeHandler(handler)
		root.setLevel(previous_level)
		logging.disable(previous_disable)


class RedirectMatcherTests(SimpleTestCase):
	'''	The shared matcher enforces exact, parsed, per-line matching and fails closed.
	'''
	def test_exact_single_entry_is_accepted(self):
		self.assertTrue(is_registered_redirect_uri(REGISTERED, REGISTERED))

	def test_either_entry_of_a_multiline_field_matches(self):
		config = 'https://a.example.com/cb\nhttps://b.example.com/cb'
		self.assertTrue(is_registered_redirect_uri('https://a.example.com/cb', config))
		self.assertTrue(is_registered_redirect_uri('https://b.example.com/cb', config))

	def test_surrounding_whitespace_and_blank_lines_are_ignored(self):
		config = '\n  https://a.example.com/cb  \r\n\n\t%s\t\n' % REGISTERED
		self.assertTrue(is_registered_redirect_uri(REGISTERED, config))
		self.assertTrue(is_registered_redirect_uri('https://a.example.com/cb', config))

	def test_shorter_path_is_rejected(self):
		self.assertFalse(is_registered_redirect_uri('https://viewer.example.com:8443/oauth', REGISTERED))

	def test_longer_path_is_rejected(self):
		self.assertFalse(is_registered_redirect_uri('%s/extra' % REGISTERED, REGISTERED))

	def test_relative_uri_is_rejected(self):
		self.assertFalse(is_registered_redirect_uri('/oauth/callback', REGISTERED))
		self.assertFalse(is_registered_redirect_uri('/', REGISTERED))

	def test_scheme_relative_uri_is_rejected(self):
		self.assertFalse(is_registered_redirect_uri('//viewer.example.com:8443/oauth/callback', REGISTERED))

	def test_hostname_prefixes_and_sibling_domains_are_rejected(self):
		'''	A requested origin that is a raw substring of the registered entry must not match.
		'''
		config = 'https://viewer.acme.co.uk/callback'
		self.assertFalse(is_registered_redirect_uri('https://viewer.acme.co', config))
		self.assertFalse(is_registered_redirect_uri('https://viewer.acme.co/callback', config))
		self.assertFalse(is_registered_redirect_uri('https://evil-viewer.acme.co.uk/callback', config))
		self.assertFalse(is_registered_redirect_uri('https://viewer.acme.co.uk.evil.io/callback', config))

	def test_different_nondefault_port_is_rejected(self):
		self.assertFalse(is_registered_redirect_uri('https://viewer.example.com:9999/oauth/callback', REGISTERED))

	def test_omitted_port_does_not_match_a_registered_nondefault_port(self):
		self.assertFalse(is_registered_redirect_uri('https://viewer.example.com/oauth/callback', REGISTERED))

	def test_default_ports_normalize(self):
		self.assertTrue(is_registered_redirect_uri('https://a.example.com:443/cb', 'https://a.example.com/cb'))
		self.assertTrue(is_registered_redirect_uri('https://a.example.com/cb', 'https://a.example.com:443/cb'))
		self.assertTrue(is_registered_redirect_uri('http://a.example.com:80/cb', 'http://a.example.com/cb'))
		self.assertFalse(is_registered_redirect_uri('http://a.example.com:443/cb', 'http://a.example.com/cb'))

	def test_scheme_and_hostname_case_normalize_but_path_case_does_not(self):
		self.assertTrue(is_registered_redirect_uri('HTTPS://VIEWER.example.COM:8443/oauth/callback', REGISTERED))
		self.assertFalse(is_registered_redirect_uri('https://viewer.example.com:8443/OAuth/callback', REGISTERED))

	def test_scheme_mismatch_is_rejected(self):
		self.assertFalse(is_registered_redirect_uri('http://viewer.example.com:8443/oauth/callback', REGISTERED))

	def test_trailing_slash_mismatch_is_rejected(self):
		self.assertFalse(is_registered_redirect_uri('%s/' % REGISTERED, REGISTERED))

	def test_percent_encoding_differences_are_rejected(self):
		self.assertFalse(is_registered_redirect_uri(
			'https://viewer.example.com:8443/oauth%2Fcallback', REGISTERED))
		self.assertFalse(is_registered_redirect_uri(
			'https://viewer.example.com:8443/%6Fauth/callback', REGISTERED))

	def test_dot_segment_variations_are_rejected(self):
		self.assertFalse(is_registered_redirect_uri(
			'https://viewer.example.com:8443/oauth/../oauth/callback', REGISTERED))
		self.assertFalse(is_registered_redirect_uri(
			'https://viewer.example.com:8443/./oauth/callback', REGISTERED))

	def test_static_query_must_match_exactly(self):
		config = 'https://a.example.com/cb?tenant=alpha&mode=viewer'
		self.assertTrue(is_registered_redirect_uri('https://a.example.com/cb?tenant=alpha&mode=viewer', config))
		self.assertFalse(is_registered_redirect_uri('https://a.example.com/cb', config))
		self.assertFalse(is_registered_redirect_uri('https://a.example.com/cb?tenant=alpha', config))
		self.assertFalse(is_registered_redirect_uri('https://a.example.com/cb?mode=viewer&tenant=alpha', config))
		self.assertFalse(is_registered_redirect_uri('https://a.example.com/cb?tenant=beta&mode=viewer', config))
		self.assertFalse(is_registered_redirect_uri(
			'https://a.example.com/cb?tenant=alpha&mode=viewer&extra=1', config))

	def test_fragment_is_rejected(self):
		self.assertFalse(is_registered_redirect_uri('%s#frag' % REGISTERED, REGISTERED))
		self.assertFalse(is_registered_redirect_uri('%s#' % REGISTERED, REGISTERED))

	def test_semicolon_path_parameter_variation_is_rejected(self):
		self.assertFalse(is_registered_redirect_uri('%s;v=1' % REGISTERED, REGISTERED))

	def test_userinfo_is_rejected(self):
		self.assertFalse(is_registered_redirect_uri(
			'https://user@viewer.example.com:8443/oauth/callback', REGISTERED))
		self.assertFalse(is_registered_redirect_uri(
			'https://user:pass@viewer.example.com:8443/oauth/callback', REGISTERED))

	def test_malformed_hostnames_ports_and_control_characters_are_rejected(self):
		self.assertFalse(is_registered_redirect_uri('https://viewer.example.com:not-a-port/cb', REGISTERED))
		self.assertFalse(is_registered_redirect_uri('https:///oauth/callback', REGISTERED))
		self.assertFalse(is_registered_redirect_uri(
			'https://viewer.example.com:8443/oauth/call\tback', REGISTERED))
		self.assertFalse(is_registered_redirect_uri(
			'https://viewer.example.com:8443/oauth/call\nback', REGISTERED))

	def test_one_malformed_entry_rejects_the_whole_configuration(self):
		'''	Only whole nonblank lines are configuration, and a line which cannot be read
			invalidates the entire registration -- an annotated or partially corrupted field
			authorizes nothing, including its well-formed entries.
		'''
		config = '# https://commented.example.com/cb\n%s' % REGISTERED
		self.assertFalse(is_registered_redirect_uri('https://commented.example.com/cb', config))
		self.assertFalse(is_registered_redirect_uri(REGISTERED, config))

	def test_a_trailing_malformed_entry_also_rejects_the_configuration(self):
		self.assertFalse(is_registered_redirect_uri(
			REGISTERED, '%s\nnot a uri' % REGISTERED))

	def test_missing_or_malformed_configuration_fails_closed(self):
		for config in (None, '', '   \n  \n', 'not a uri', 'ftp://a.example.com/cb', '/relative/cb'):
			self.assertFalse(is_registered_redirect_uri(REGISTERED, config))

	def test_a_registered_query_may_not_declare_a_response_parameter(self):
		'''	An appended response parameter would otherwise be ambiguous with a configured one.
		'''
		for reserved in ('code', 'state', 'nonce', 'next'):
			config = 'https://a.example.com/cb?%s=x' % reserved
			self.assertFalse(is_registered_redirect_uri(config, config),
				'"%s" was accepted in a registered query' % reserved)
			with self.assertRaises(ValidationError):
				validate_redirect_uri_configuration(config)

	def test_a_percent_encoded_response_parameter_name_is_recognized(self):
		'''	A client decodes the parameter name before reading it, so an encoded spelling of
			a reserved name is the same declaration and is rejected the same way.
		'''
		for encoded in ('%63ode', 'co%64e', 'sta%74e', '%6Eext', 'no%6Ece'):
			config = 'https://a.example.com/cb?%s=x' % encoded
			self.assertFalse(is_registered_redirect_uri(config, config),
				'"%s" was accepted in a registered query' % encoded)
			with self.assertRaises(ValidationError):
				validate_redirect_uri_configuration(config)

	def test_an_unrelated_encoded_parameter_name_is_still_accepted(self):
		config = 'https://a.example.com/cb?ten%61nt=alpha'
		self.assertTrue(is_registered_redirect_uri(config, config))

	def test_the_reserved_parameter_set_is_supplied_by_the_caller(self):
		'''	Which names a response generates is a property of that response, so a caller
			building a different one supplies its own set instead of inheriting this flow's.
		'''
		grant_reserved = ('access_token', 'id_token', 'token_type')

		# A name this flow reserves is unremarkable to a caller which does not generate it
		config = 'https://a.example.com/cb?code=x'
		self.assertFalse(is_registered_redirect_uri(config, config))
		self.assertTrue(is_registered_redirect_uri(config, config,
			reserved_params=grant_reserved))

		# ...and the caller's own names are rejected for it
		config = 'https://a.example.com/cb?access_token=x'
		self.assertTrue(is_registered_redirect_uri(config, config))
		self.assertFalse(is_registered_redirect_uri(config, config,
			reserved_params=grant_reserved))

	def test_the_default_reserved_set_is_unchanged(self):
		'''	Callers which do not pass a set keep this flow's policy exactly.
		'''
		for reserved in ('code', 'state', 'nonce', 'next'):
			config = 'https://a.example.com/cb?%s=x' % reserved
			self.assertFalse(is_registered_redirect_uri(config, config))

	def test_malformed_request_values_fail_closed(self):
		for requested in (None, '', 'not a uri', 'javascript:alert(1)', 'ftp://a.example.com/cb'):
			self.assertFalse(is_registered_redirect_uri(requested, REGISTERED))

	def test_parse_redirect_uri_rejects_non_string_values(self):
		self.assertIsNone(parse_redirect_uri(None))
		self.assertIsNone(parse_redirect_uri(42))

	def test_configuration_validator_accepts_blank_and_valid_fields(self):
		validate_redirect_uri_configuration(None)
		validate_redirect_uri_configuration('')
		validate_redirect_uri_configuration('%s\nhttps://a.example.com/cb?tenant=alpha' % REGISTERED)

	def test_configuration_validator_rejects_invalid_entries(self):
		for config in ('not a uri', '/relative/cb', '%s\nftp://a.example.com/cb' % REGISTERED,
				'https://user@a.example.com/cb', '%s#frag' % REGISTERED):
			with self.assertRaises(ValidationError):
				validate_redirect_uri_configuration(config)


class ContinuationValidationTests(SimpleTestCase):
	'''	`next` carries application continuation state; it never receives the authorization
		response, so it is validated for safety rather than for registration. Site relative
		paths are the expected form; an absolute value must be an exact registered URI.
	'''
	def test_site_relative_paths_are_valid(self):
		for value in ('/', '/studies/1', '/viewer/study/123?tab=segmentation', '/a%2Fb'):
			self.assertTrue(is_valid_continuation(value, REGISTERED),
				'continuation "%s" was rejected' % value)

	def test_an_exact_registered_uri_is_valid(self):
		self.assertTrue(is_valid_continuation(REGISTERED, REGISTERED))

	def test_scheme_relative_and_absolute_offsite_values_are_rejected(self):
		for value in (
				'//viewer.example.com:8443/x',                      # scheme relative
				'///evil.example.com',                              # treated as absolute by browsers
				'/\\evil.example.com',                              # backslash spelling of the above
				'/\\/evil.example.com',
				'https://evil.example.com/steal',                   # unregistered origin
				'https://viewer.example.com:8443/viewer/study/123', # registered origin, unregistered URI
				'javascript:alert(1)',
				'/x\r\nSet-Cookie: a=b'):                           # control characters
			self.assertFalse(is_valid_continuation(value, REGISTERED),
				'continuation "%s" was wrongly accepted' % value)

	def test_empty_values_are_rejected(self):
		for value in (None, '', 42):
			self.assertFalse(is_valid_continuation(value, REGISTERED))

	def test_an_absolute_value_requires_valid_configuration(self):
		for config in (None, '', 'not a uri'):
			self.assertFalse(is_valid_continuation(REGISTERED, config))


class ResponseParameterAppendTests(SimpleTestCase):
	'''	Generated response parameters are appended without parsing or re-encoding the
		registered static query, so an operator's exact bytes survive.
	'''
	def test_parameters_are_appended_to_a_uri_without_a_query(self):
		self.assertEqual(
			append_response_parameters('https://a.example.com/cb', {'code': 'abc'}),
			'https://a.example.com/cb?code=abc')

	def test_a_registered_query_is_preserved_byte_for_byte(self):
		'''	Duplicate keys, blank values, parameter order, and percent-encoded
			representation all survive: the existing query is never reparsed.
		'''
		registered = 'https://a.example.com/cb?scope=a&scope=b&flag=&x=%2f&Z=1'
		appended = append_response_parameters(registered, {'code': 'abc'})

		self.assertTrue(appended.startswith('%s&' % registered))
		self.assertEqual(appended, '%s&code=abc' % registered)

	def test_no_parameters_leaves_the_uri_untouched(self):
		registered = 'https://a.example.com/cb?scope=a&scope=b'
		self.assertEqual(append_response_parameters(registered, {}), registered)
		self.assertEqual(append_response_parameters(registered, {'code': None}), registered)

	def test_a_trailing_separator_is_not_duplicated(self):
		self.assertEqual(
			append_response_parameters('https://a.example.com/cb?', {'code': 'abc'}),
			'https://a.example.com/cb?code=abc')

	def test_appended_values_are_encoded(self):
		appended = append_response_parameters('https://a.example.com/cb', {'next': '/a b/c?d=1'})
		self.assertEqual(appended, 'https://a.example.com/cb?next=%2Fa+b%2Fc%3Fd%3D1')


class DataServiceOAuthTestCase(TestCase):
	'''	Shared fixture: a staff user (data services allow staff by default), an authorization
		server, and a data service with a registered callback URI.
	'''
	def setUp(self):
		self.user = User.objects.create_user('mateus.werneck', password='x', is_staff=True)
		self.client.force_login(self.user)

		self.authserver = fixtures.create_authserver()
		self.dataservice = DataService.objects.create(
			description='Test data service', openid_allow_auth=True,
			openid_callback_url=REGISTERED, authserver=self.authserver)

	def login_params(self, **overrides):
		params = {
			'response_type': 'code',
			'redirect_uri': REGISTERED,
			'client_id': self.dataservice.openid_client_id,
			'state': 'state-token', 'nonce': 'nonce-token',
		}
		params.update(overrides)
		return { key: val for key, val in params.items() if val is not None }

	def initiate(self, **overrides):
		'''	Run the login redirect so the authorization transaction is recorded against the
			test client's session, as it would be before the callback is reached.
		'''
		with mock.patch.object(SocialAuthorizationServer, 'create_authorization_url',
				return_value='https://idp.example.com/o/authorize/'):
			return self.client.get(
				reverse('visionaire-api:data-service-openid-login', args=(self.dataservice.pk,)),
				self.login_params(**overrides))


class DataServiceLoginRedirectTests(DataServiceOAuthTestCase):
	'''	Initiation: the redirect view validates redirect_uri and any continuation before
		forwarding to the identity provider.
	'''
	IDP_URL = 'https://idp.example.com/o/authorize/'

	def get_login(self, **overrides):
		with mock.patch.object(SocialAuthorizationServer, 'create_authorization_url',
				return_value=self.IDP_URL) as create_url:
			response = self.client.get(self.dataservice.url_login, self.login_params(**overrides))
		return response, create_url

	def test_registered_redirect_proceeds_to_the_identity_provider(self):
		response, create_url = self.get_login()

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response['Location'], self.IDP_URL)
		create_url.assert_called_once()

	def test_unregistered_redirect_is_rejected_before_any_idp_redirect(self):
		for redirect_uri in (
				'https://viewer.example.com:8443/oauth',            # shorter path
				'https://viewer.example.com',                       # bare origin
				'https://viewer.example.com/oauth/callback',        # effective-port mismatch
				'/oauth/callback',                                  # relative
				'%s/extra' % REGISTERED):                           # longer path
			response, create_url = self.get_login(redirect_uri=redirect_uri)

			self.assertEqual(response.status_code, 403,
				'redirect_uri "%s" was not rejected' % redirect_uri)
			create_url.assert_not_called()

	def test_next_cannot_bypass_redirect_uri_validation(self):
		response, create_url = self.get_login(
			redirect_uri='https://evil.example.com/steal', next='/studylist')

		self.assertEqual(response.status_code, 403)
		create_url.assert_not_called()

	def test_a_relative_continuation_proceeds(self):
		response, create_url = self.get_login(next='/viewer/study/123')

		self.assertEqual(response.status_code, 302)
		create_url.assert_called_once()

	def test_an_offsite_continuation_is_rejected(self):
		for next_value in ('https://evil.example.com/steal',
				'https://viewer.example.com:8443/viewer/study/123'):
			response, create_url = self.get_login(next=next_value)

			self.assertEqual(response.status_code, 403,
				'continuation "%s" was not rejected' % next_value)
			create_url.assert_not_called()

	def test_missing_callback_configuration_fails_with_403_not_500(self):
		self.dataservice.openid_callback_url = None
		self.dataservice.save()

		response, create_url = self.get_login()

		self.assertEqual(response.status_code, 403)
		create_url.assert_not_called()


class DataServiceLoginCallbackTests(DataServiceOAuthTestCase):
	'''	Completion: the callback revalidates the original redirect_uri before minting a data
		service authorization code, and only a registered target receives the code.
	'''
	def get_callback(self, initiate=None, **overrides):
		'''	Complete a round trip: initiate the login so the transaction is recorded, then
			present the callback. `initiate` overrides the parameters used at initiation, so a
			test can present a callback which differs from the request that began the flow.
		'''
		self.initiate(**(initiate if initiate is not None else overrides))
		return self.client.get(self.dataservice.url_callback, self.login_params(**overrides))

	def assertNoCodeIssued(self, response):
		'''	A rejected callback must not deliver an authorization code anywhere: the response
			is a 403 with no redirect target.
		'''
		self.assertEqual(response.status_code, 403)
		self.assertNotIn('Location', response)

	def test_registered_redirect_receives_the_authorization_code(self):
		response = self.get_callback()

		self.assertEqual(response.status_code, 302)
		base, _, query = response['Location'].partition('?')
		self.assertEqual(base, REGISTERED)

		params = parse_qs(query)
		self.assertTrue(params.get('code'))
		self.assertEqual(params.get('state'), ['state-token'])
		self.assertEqual(params.get('nonce'), ['nonce-token'])

	def test_a_registered_static_query_survives_byte_for_byte(self):
		'''	Duplicate keys, blank values, parameter order, and percent-encoded representation
			are all preserved: the response parameters are appended to the raw registered
			query rather than merged into a reparsed one.
		'''
		registered = 'https://viewer.example.com/cb?scope=a&scope=b&flag=&x=%2f&Z=1'
		self.dataservice.openid_callback_url = registered
		self.dataservice.save()

		response = self.get_callback(redirect_uri=registered)

		self.assertEqual(response.status_code, 302)
		self.assertTrue(response['Location'].startswith('%s&' % registered),
			'registered query was rewritten: %s' % response['Location'])
		self.assertTrue(parse_qs(urlsplit(response['Location']).query).get('code'))

	def test_unregistered_redirects_are_rejected_without_issuing_a_code(self):
		for redirect_uri in (
				'https://viewer.example.com:8443/oauth',            # shorter path
				'https://viewer.example.com',                       # bare origin
				'https://viewer.example.com/oauth/callback',        # effective-port mismatch
				'/oauth/callback',                                  # relative
				'%s?extra=1' % REGISTERED):                         # query mismatch
			self.assertNoCodeIssued(self.get_callback(redirect_uri=redirect_uri))

	def test_a_continuation_is_carried_to_the_exact_callback(self):
		'''	The continuation reaches the client as a parameter on the registered callback, so
			the client applies it after exchanging the code. It does not move the response.
		'''
		response = self.get_callback(next='/viewer/study/123')

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response['Location'].partition('?')[0], REGISTERED)

		params = parse_qs(urlsplit(response['Location']).query)
		self.assertEqual(params.get('next'), ['/viewer/study/123'])
		self.assertTrue(params.get('code'))

	def test_a_same_origin_deep_link_never_receives_the_code(self):
		'''	Sharing an origin with a registered callback does not make a route a credential
			receiver: an absolute continuation must be an exact registered URI.
		'''
		self.assertNoCodeIssued(
			self.get_callback(next='https://viewer.example.com:8443/viewer/study/123'))

	def test_an_offsite_continuation_is_rejected_without_issuing_a_code(self):
		for next_value in ('https://evil.example.com/steal', '//evil.example.com',
				'/\\evil.example.com'):
			self.assertNoCodeIssued(self.get_callback(next=next_value))

	def test_next_with_an_unregistered_redirect_uri_is_still_rejected(self):
		self.assertNoCodeIssued(self.get_callback(
			redirect_uri='https://evil.example.com/steal', next='/studylist'))

	def test_missing_callback_configuration_fails_with_403_not_500(self):
		self.dataservice.openid_callback_url = None
		self.dataservice.save()

		self.assertNoCodeIssued(self.get_callback())

	def test_an_expired_transaction_is_rejected(self):
		'''	A login which does not return within the window is abandoned, so its record stops
			being an accepted answer rather than lasting for the session.
		'''
		self.initiate()

		with mock.patch('wgtauth.transactions.time.time',
				return_value=time.time() + TRANSACTION_MAX_AGE + 60):
			response = self.client.get(self.dataservice.url_callback, self.login_params())

		self.assertNoCodeIssued(response)

	def test_a_transaction_within_the_window_is_accepted(self):
		'''	Control for the expiry case above.
		'''
		self.initiate()

		with mock.patch('wgtauth.transactions.time.time',
				return_value=time.time() + 30):
			response = self.client.get(self.dataservice.url_callback, self.login_params())

		self.assertEqual(response.status_code, 302)

	def test_a_callback_without_a_pending_transaction_is_rejected(self):
		'''	The callback is only honoured for a flow this application started.
		'''
		self.assertNoCodeIssued(
			self.client.get(self.dataservice.url_callback, self.login_params()))

	def test_a_callback_cannot_be_replayed(self):
		'''	The transaction is consumed on first use.
		'''
		self.assertEqual(self.get_callback().status_code, 302)
		self.assertNoCodeIssued(
			self.client.get(self.dataservice.url_callback, self.login_params()))

	def test_a_modified_redirect_uri_is_rejected(self):
		'''	Substituting a different registered callback after the flow began does not
			redirect the code to it.
		'''
		self.dataservice.openid_callback_url = '%s\nhttps://other.example.com/cb' % REGISTERED
		self.dataservice.save()

		self.assertNoCodeIssued(self.get_callback(
			initiate={}, redirect_uri='https://other.example.com/cb'))

	def test_a_modified_continuation_is_rejected(self):
		'''	A continuation introduced or altered after initiation is not honoured; the value
			recorded at initiation is authoritative.
		'''
		response = self.get_callback(initiate={}, next='/injected')

		self.assertNoCodeIssued(response)

	def test_a_modified_state_is_rejected(self):
		self.assertNoCodeIssued(self.get_callback(initiate={}, state='other-state'))

	def test_a_modified_nonce_is_rejected(self):
		self.assertNoCodeIssued(self.get_callback(initiate={}, nonce='other-nonce'))

	def test_mismatched_client_id_is_rejected(self):
		self.assertNoCodeIssued(self.get_callback(client_id='other-client'))

	def test_client_id_variants_are_rejected(self):
		'''	The client ID is an identity boundary, so a prefix, suffix, or case variant of the
			real value is not accepted.
		'''
		real = self.dataservice.openid_client_id
		for variant in (real[:-1], '%sx' % real, real.lower(), real.upper(), ' %s' % real):
			if variant == real:
				continue
			self.assertNoCodeIssued(self.get_callback(client_id=variant),
				)

	def test_a_missing_state_is_rejected(self):
		self.assertNoCodeIssued(self.get_callback(state=None))

	def test_the_issued_code_is_not_written_to_the_logs(self):
		'''	The authorization response carries a redeemable credential, so neither the code
			nor the redirect carrying it may be recorded.
		'''
		with capture_logs() as emitted:
			response = self.get_callback()

		self.assertEqual(response.status_code, 302)
		code = parse_qs(urlsplit(response['Location']).query)['code'][0]

		self.assertNotIn(code, emitted())
		self.assertNotIn(response['Location'], emitted())

	def test_a_rejected_redirect_is_not_written_to_the_logs(self):
		'''	A refused value is attacker supplied, so failures record the service and the
			reason rather than the value presented.
		'''
		unregistered = 'https://evil.example.com/steal'

		with capture_logs() as emitted:
			self.assertNoCodeIssued(self.get_callback(redirect_uri=unregistered))

		self.assertNotIn(unregistered, emitted())
