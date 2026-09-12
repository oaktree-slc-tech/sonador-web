'''	Tests for the deployment check covering the login round trip protections of the default
	authorization server's identity provider: through the function, through the check
	framework, and through the management command the container entrypoint runs.
'''
import os, subprocess, sys, tempfile, textwrap

from unittest import mock

from django.core.checks import run_checks, Tags
from django.core.management import call_command
from django.core.management.base import CommandError, SystemCheckError
from django.db import DatabaseError
from django.test import TestCase, SimpleTestCase, override_settings

from ..checks import check_default_authserver_login_protections, login_protection_errors
from . import fixtures


ENTRYPOINT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
	os.path.dirname(os.path.abspath(__file__))))), 'config', 'entrypoint.sh')


class LoginProtectionCheckTests(TestCase):

	def protected_authserver(self, **relaxed):
		authserver = fixtures.create_authserver(default=True)
		provider = authserver.provider
		provider.endpoint_jwks = '/o/.well-known/jwks.json'
		provider.oidc_issuer = 'https://idp.example.com/o'
		provider.oidc_id_token_required = True
		for field, value in relaxed.items():
			setattr(provider, field, value)
		provider.save()
		return authserver

	def errors(self):
		return [msg for msg in check_default_authserver_login_protections(None, databases=['default'])
			if msg.id == 'visionaire.E004']

	def test_no_default_authorization_server_is_not_an_error(self):
		self.assertEqual(self.errors(), [])

	def test_a_fully_protected_provider_is_not_an_error(self):
		self.protected_authserver()
		self.assertEqual(self.errors(), [])

	def test_a_relaxed_protection_is_named(self):
		self.protected_authserver(oidc_pkce=False)

		errors = self.errors()
		self.assertEqual(len(errors), 1)
		self.assertIn('no PKCE challenge is sent', errors[0].msg)
		self.assertNotIn('nonce', errors[0].msg)

	def test_every_relaxed_protection_is_listed(self):
		self.protected_authserver(oidc_state=False, oidc_nonce=False,
			oidc_id_token_required=False, oidc_issuer='', endpoint_jwks='')

		errors = self.errors()
		self.assertEqual(len(errors), 1)
		for reason in ('state sent to the provider is not verified', 'not bound to the login',
				'without an ID token is accepted', 'no issuer is configured',
				'signature is not verified'):
			self.assertIn(reason, errors[0].msg)

	def test_without_a_database_the_check_reads_nothing(self):
		self.protected_authserver(oidc_nonce=False)
		self.assertEqual(check_default_authserver_login_protections(None), [])

	def test_the_check_is_registered(self):
		self.protected_authserver(oidc_nonce=False)
		ids = [msg.id for msg in run_checks(tags=[Tags.security], databases=['default'])]
		self.assertIn('visionaire.E004', ids)


class CheckCommandTests(TestCase):
	'''	The gate the entrypoint relies on: `manage.py check --database default` exits
		nonzero for a relaxed default provider and passes for a protected one.
	'''
	def test_a_relaxed_provider_fails_the_command(self):
		LoginProtectionCheckTests.protected_authserver(self, oidc_issuer='')

		with self.assertRaises(SystemCheckError) as raised:
			call_command('check', databases=['default'], verbosity=0)
		self.assertIn('visionaire.E004', str(raised.exception))

	def test_a_protected_provider_passes_the_command(self):
		LoginProtectionCheckTests.protected_authserver(self)
		call_command('check', databases=['default'], verbosity=0)

	def test_the_entrypoint_runs_the_database_checks(self):
		with open(ENTRYPOINT) as f:
			script = f.read()
		self.assertIn('manage.py imaging-env-init || exit 1', script)
		self.assertIn('manage.py check --database default || exit 1', script)
		self.assertIn('manage.py verify-login-protections || exit 1', script)


class VerifyLoginProtectionsCommandTests(TestCase):
	'''	The strict post-initialization read: a relaxed provider and an unreadable provider
		table both fail the command, so the entrypoint stops in either case.
	'''
	def test_a_protected_provider_passes(self):
		LoginProtectionCheckTests.protected_authserver(self)
		call_command('verify-login-protections', verbosity=0)

	def test_no_default_authorization_server_passes(self):
		call_command('verify-login-protections', verbosity=0)

	def test_a_relaxed_provider_fails(self):
		LoginProtectionCheckTests.protected_authserver(self, oidc_pkce=False)

		with self.assertRaises(CommandError) as raised:
			call_command('verify-login-protections', verbosity=0)
		self.assertIn('no PKCE challenge is sent', str(raised.exception))

	def test_an_unreadable_provider_table_fails(self):
		with mock.patch('visionaire.auth.views.base.get_default_authserver',
				side_effect=DatabaseError('relation does not exist')):
			with self.assertRaises(CommandError) as raised:
				call_command('verify-login-protections', verbosity=0)
		self.assertIn('Unable to read the default authorization server', str(raised.exception))

	@override_settings(SILENCED_SYSTEM_CHECKS=['visionaire.E004'])
	def test_a_silenced_relaxation_passes(self):
		'''	A deployment which relaxes a protection for a provider lacking the feature
			silences the check in its settings; the strict read honours the same policy.
		'''
		LoginProtectionCheckTests.protected_authserver(self, oidc_pkce=False)
		call_command('verify-login-protections', verbosity=0)

	@override_settings(SILENCED_SYSTEM_CHECKS=['visionaire.E004'])
	def test_silencing_does_not_cover_an_unreadable_provider_table(self):
		with mock.patch('visionaire.auth.views.base.get_default_authserver',
				side_effect=DatabaseError('relation does not exist')):
			with self.assertRaises(CommandError):
				call_command('verify-login-protections', verbosity=0)

	def test_the_system_check_tolerates_what_the_command_does_not(self):
		'''	`migrate` runs the system check before applying anything, so an unreadable table
			reports nothing there; the strict read raises.
		'''
		with mock.patch('visionaire.auth.views.base.get_default_authserver',
				side_effect=DatabaseError('relation does not exist')):
			self.assertEqual(login_protection_errors(strict=False), [])
			with self.assertRaises(DatabaseError):
				login_protection_errors(strict=True)


class EntrypointTests(SimpleTestCase):
	'''	The container entrypoint, run against a stand-in manage.py: a failing initialization
		or verification step stops the script before the server is started.
	'''
	FAKE_MANAGE = textwrap.dedent('''\
		import os, sys
		failing = os.environ.get('FAIL_STEP', '')
		open(os.environ['STEP_LOG'], 'a').write(sys.argv[1] + '\\n')
		sys.exit(1 if sys.argv[1] == failing else 0)
	''')
	FAKE_SERVER = "import os; open(os.environ['STEP_LOG'], 'a').write('uvicorn\\n')\n"

	def run_entrypoint(self, fail_step=''):
		root = tempfile.mkdtemp()
		os.makedirs(os.path.join(root, 'sonador'))
		with open(os.path.join(root, 'sonador', 'manage.py'), 'w') as f:
			f.write(self.FAKE_MANAGE)
		with open(os.path.join(root, 'sonador', 'uvicorn-sonador.py'), 'w') as f:
			f.write(self.FAKE_SERVER)
		step_log = os.path.join(root, 'steps.log')

		env = dict(os.environ, PROJECT_ROOT=root, CONFIG_ROOT=os.path.join(root, 'config'),
			STEP_LOG=step_log, FAIL_STEP=fail_step, PATH=os.environ.get('PATH', ''))
		result = subprocess.run(['sh', ENTRYPOINT], env=env, capture_output=True, timeout=60)

		steps = open(step_log).read().split() if os.path.exists(step_log) else []
		return result.returncode, steps

	def test_a_failed_initialization_stops_before_the_server(self):
		code, steps = self.run_entrypoint(fail_step='imaging-env-init')
		self.assertNotEqual(code, 0)
		self.assertEqual(steps, ['imaging-env-init'])

	def test_a_failed_verification_stops_before_the_server(self):
		code, steps = self.run_entrypoint(fail_step='verify-login-protections')
		self.assertNotEqual(code, 0)
		self.assertNotIn('uvicorn', steps)
		self.assertEqual(steps[-1], 'verify-login-protections')

	def test_a_clean_start_reaches_the_server(self):
		code, steps = self.run_entrypoint()
		self.assertEqual(code, 0)
		self.assertEqual(steps, ['imaging-env-init', 'check', 'verify-login-protections', 'uvicorn'])
