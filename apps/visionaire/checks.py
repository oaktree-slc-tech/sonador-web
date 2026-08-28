'''	Deployment checks for the session storage Data Service authentication depends on.

	Data Service OAuth holds per-login authorization state in `request.session` between the
	login redirect and the callback. Those requests are served by different workers and are
	separated by redirects through the auth server and the identity provider, so the state has
	to be read back from the primary relational database rather than from any intermediate
	copy. That is a property of the configured storage rather than of the code, so it is
	asserted at startup instead of assumed.
'''
from django.core.checks import Error, register, Tags


# The only session backend which reads session data from the database. `cached_db` writes
# through to the database but serves reads from a cache, so authorization state can be read
# from a copy the database no longer agrees with.
DATABASE_SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# Database backends Sonador is deployed and packaged against
SUPPORTED_DATABASE_BACKENDS = (
	'django.db.backends.postgresql',
	'django.db.backends.postgresql_psycopg2',
)


@register(Tags.security)
def check_session_storage(app_configs, **kwargs):
	'''	Sessions must be read from and written to the database.
	'''
	from django.conf import settings

	engine = getattr(settings, 'SESSION_ENGINE', '')
	if engine == DATABASE_SESSION_ENGINE:
		return []

	return [Error(
		'SESSION_ENGINE "%s" does not read session data from the database.' % engine,
		hint='Data Service authorization state is written by the worker serving the login '
			'redirect and read by the worker receiving the callback. Set SESSION_ENGINE to '
			'"%s". "cached_db" is not sufficient: it serves reads from a cache.'
			% DATABASE_SESSION_ENGINE,
		id='visionaire.E001')]


@register(Tags.database)
def check_session_database_routing(app_configs, **kwargs):
	'''	The Session model must read and write the primary database, and that database must be
		one Sonador is supported against.

		Routing is resolved rather than inferred from `DATABASES['default']`: a router may
		send session reads or writes to another alias, including a read replica which can
		return authorization state the primary has already changed.
	'''
	from django.conf import settings
	from django.db import router, DEFAULT_DB_ALIAS
	from django.contrib.sessions.models import Session

	errors = []

	# Mirror the calls the session backend makes: `SessionStore.save()` routes with the
	# instance it is about to write, so a router which inspects the instance would otherwise
	# be able to satisfy this check and still send the write elsewhere.
	read_alias = router.db_for_read(Session) or DEFAULT_DB_ALIAS
	write_alias = router.db_for_write(Session, instance=Session()) or DEFAULT_DB_ALIAS

	for label, alias in (('read', read_alias), ('write', write_alias)):
		if alias != DEFAULT_DB_ALIAS:
			errors.append(Error(
				'Session %s operations are routed to the "%s" database.' % (label, alias),
				hint='Data Service authorization state must be read back from the primary '
					'database. Route the Session model to "%s".' % DEFAULT_DB_ALIAS,
				id='visionaire.E003'))

	engine = (settings.DATABASES.get(DEFAULT_DB_ALIAS) or {}).get('ENGINE', '')
	if engine not in SUPPORTED_DATABASE_BACKENDS:
		errors.append(Error(
			'Unsupported primary database backend "%s".' % engine,
			hint='Sonador is deployed and packaged against PostgreSQL; only its bindings are '
				'shipped with the application. Set the "%s" database ENGINE to %s.'
				% (DEFAULT_DB_ALIAS, SUPPORTED_DATABASE_BACKENDS[0]),
			id='visionaire.E002'))

	return errors
