'''	Tests for the deployment checks covering session storage.

	Data Service OAuth keeps per-login authorization state in the session between the login
	redirect and the callback. The callback is served by a different worker after several
	redirects, so that state has to be read back from the primary database rather than from an
	intermediate copy. Nothing in the request path can enforce that, which is why it is
	checked at startup.

	The checks are exercised through Django's registered check framework as well as directly,
	so a check which stops being registered fails here rather than passing silently.
'''
from django.core.checks import run_checks, Tags
from django.test import SimpleTestCase, override_settings

from ..checks import check_session_storage, check_session_database_routing, \
	DATABASE_SESSION_ENGINE


POSTGRES = {'default': {'ENGINE': 'django.db.backends.postgresql'}}


class SessionRouter:
	'''	Router which sends every Session operation to a secondary database.
	'''
	def db_for_read(self, model, **hints):
		return 'replica' if model._meta.model_name == 'session' else None

	def db_for_write(self, model, **hints):
		return 'replica' if model._meta.model_name == 'session' else None


class SessionReadRouter(SessionRouter):
	'''	Router which reads the Session model from a replica but writes to the primary.
	'''
	def db_for_write(self, model, **hints):
		return None


class InstanceAwareSessionRouter:
	'''	Router which only redirects the write when it is given the instance being saved.

		The session backend routes its write as `db_for_write(model, instance=obj)`, so a
		router of this shape decides on the real write while a routing query made without an
		instance sees nothing unusual.
	'''
	def db_for_read(self, model, **hints):
		return None

	def db_for_write(self, model, **hints):
		if model._meta.model_name == 'session' and hints.get('instance') is not None:
			return 'replica'

		return None


def check_ids(errors):
	return sorted(error.id for error in errors)


class SessionEngineCheckTests(SimpleTestCase):

	@override_settings(SESSION_ENGINE=DATABASE_SESSION_ENGINE)
	def test_the_database_session_store_passes(self):
		self.assertEqual(check_session_storage(None), [])

	def test_a_cache_reading_session_store_is_rejected(self):
		'''	`cached_db` writes through to the database but serves reads from a cache, so
			authorization state can be read from a copy the database no longer agrees with.
			The remaining backends do not durably share it at all.
		'''
		for engine in ('django.contrib.sessions.backends.cached_db',
				'django.contrib.sessions.backends.cache',
				'django.contrib.sessions.backends.signed_cookies',
				'django.contrib.sessions.backends.file'):
			with override_settings(SESSION_ENGINE=engine):
				errors = check_session_storage(None)

			self.assertEqual(check_ids(errors), ['visionaire.E001'],
				'session engine "%s" was accepted' % engine)

	def test_the_deployed_configuration_passes(self):
		self.assertEqual(check_session_storage(None), [])


class SessionRoutingCheckTests(SimpleTestCase):

	@override_settings(DATABASES=POSTGRES)
	def test_the_primary_database_passes(self):
		self.assertEqual(check_session_database_routing(None), [])

	@override_settings(DATABASES=POSTGRES, DATABASE_ROUTERS=[SessionRouter()])
	def test_sessions_routed_to_another_database_are_rejected(self):
		'''	A router can move session storage off the primary while the default database
			remains PostgreSQL, so the routing is resolved rather than inferred.
		'''
		self.assertEqual(check_ids(check_session_database_routing(None)),
			['visionaire.E003', 'visionaire.E003'])

	@override_settings(DATABASES=POSTGRES, DATABASE_ROUTERS=[SessionReadRouter()])
	def test_sessions_read_from_a_replica_are_rejected(self):
		'''	A replica can return authorization state the primary has already changed.
		'''
		self.assertEqual(check_ids(check_session_database_routing(None)), ['visionaire.E003'])

	@override_settings(DATABASES=POSTGRES, DATABASE_ROUTERS=[InstanceAwareSessionRouter()])
	def test_an_instance_aware_write_router_is_rejected(self):
		'''	The check routes the way the session backend does -- with the instance being
			saved -- so a router which decides on the instance cannot pass it and still send
			the real write elsewhere.
		'''
		self.assertEqual(check_ids(check_session_database_routing(None)), ['visionaire.E003'])

	def test_unsupported_database_backends_are_rejected(self):
		'''	Only PostgreSQL bindings are packaged with the application.
		'''
		for engine in ('django.db.backends.sqlite3', 'django.db.backends.mysql', ''):
			with override_settings(DATABASES={'default': {'ENGINE': engine}}):
				errors = check_session_database_routing(None)

			self.assertEqual(check_ids(errors), ['visionaire.E002'],
				'database engine "%s" was accepted' % engine)

	def test_the_deployed_configuration_passes(self):
		self.assertEqual(check_session_database_routing(None), [])


class RegisteredCheckTests(SimpleTestCase):
	'''	The checks must be reachable through `manage.py check`, not merely importable.
	'''
	def test_the_checks_are_registered(self):
		with override_settings(SESSION_ENGINE='django.contrib.sessions.backends.cached_db',
				DATABASE_ROUTERS=[SessionRouter()]):
			reported = check_ids(run_checks(tags=[Tags.security, Tags.database]))

		self.assertIn('visionaire.E001', reported)
		self.assertIn('visionaire.E003', reported)

	def test_the_deployed_configuration_reports_no_errors(self):
		reported = [error for error in run_checks(tags=[Tags.security, Tags.database])
			if error.id.startswith('visionaire.')]

		self.assertEqual(reported, [])
