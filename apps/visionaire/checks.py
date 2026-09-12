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


# Identity provider record fields which each keep one login round trip protection on, and
# what a relaxed one means for the platform login
LOGIN_PROTECTION_FIELDS = (
	('oidc_state', 'the state sent to the provider is not verified'),
	('oidc_pkce', 'no PKCE challenge is sent'),
	('oidc_nonce', 'a returned ID token is not bound to the login'),
	('oidc_id_token_required', 'a login without an ID token is accepted'),
	('oidc_issuer', 'no issuer is configured for ID tokens'),
	('endpoint_jwks', 'the ID token signature is not verified'),
)


def login_protection_errors(strict=False):
	'''	Errors for a default authorization server whose identity provider relaxes a login
		round trip protection.

		@input strict (bool): raise a database error rather than returning nothing. The
			system check runs before migrations too (`migrate` checks first), when the
			provider table may lack the columns read here, so it tolerates the read
			failing; the post-initialization command does not.

		@returns list of Error
	'''
	from django.db import DatabaseError

	from .auth.views.base import get_default_authserver

	try: authserver = get_default_authserver()
	except DatabaseError:
		if strict:
			raise
		return []

	if authserver is None:
		return []

	relaxed = [reason for field, reason in LOGIN_PROTECTION_FIELDS
		if not getattr(authserver.provider, field, None)]
	if not relaxed:
		return []

	return [Error(
		'Identity provider "%s" behind the default authorization server "%s" relaxes login '
		'protections: %s.' % (authserver.provider.name, authserver.description, '; '.join(relaxed)),
		hint='Enable the protection on the identity provider record. The Acorn provider supports '
			'all of them: request the openid scope in the authorization URL parameters, set the '
			'issuer to the Acorn OpenID issuer (its /o/.well-known/openid-configuration names it), '
			'and name /o/.well-known/jwks.json as the JWKS endpoint. A provider which cannot '
			'support one is accommodated by adding "visionaire.E004" to SILENCED_SYSTEM_CHECKS.',
		id='visionaire.E004')]


@register(Tags.security, Tags.database)
def check_default_authserver_login_protections(app_configs, databases=None, **kwargs):
	'''	The platform login runs through the default authorization server, so its provider
		must keep every protection of the identity provider round trip on. The Acorn
		provider supports all of them, so a relaxed one stops the deployment rather than
		serving a login without it; a deployment which has to relax one for another
		provider silences `visionaire.E004` deliberately in its settings.

		Reads the provider record, so it runs only when the check framework names the
		databases it may use: `migrate`, and `check --database default`. `migrate` runs it
		before applying anything, so a read which fails there reports nothing; the strict
		read is `verify-login-protections`, which the container entrypoint runs once the
		schema is in place.
	'''
	if not databases:
		return []

	return login_protection_errors(strict=False)
