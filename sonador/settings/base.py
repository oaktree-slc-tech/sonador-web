""" Django settings for Sonador: this module parsees a Sonador site config, verifies
    the provided settings, and makes them available for the instance.
"""

import os, sys, mimetypes, six, datetime, warnings
from configobj import ConfigObj
from datetime import date

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuration helper methods
CONFIG_POSITIVE = ('true', 'yes', 'affirmative', 'yup', 'y', '1', 't')
def config_str2bool(boolstr):
    if isinstance(boolstr, bool): return boolstr
    if isinstance(boolstr, six.string_types):
        return boolstr.lower() in CONFIG_POSITIVE
    return False

# Retrieve site.config path
if not os.path.exists(os.environ.get('SONADOR_SITECONFIG', '')):
    raise NameError('Unable to locate a valid site.config file for the project. '
        + 'Please check the "SONADOR_SITECONFIG" environment variable.')

PROJECT_ROOT = BASE_DIR
PROJECT_CONFIGURATION_ROOT = os.path.join(PROJECT_ROOT, 'sonador')
RESOURCE_ROOT = os.path.join(PROJECT_ROOT, 'resources')

# Load site.config settings
siteconfig = ConfigObj(os.environ.get('SONADOR_SITECONFIG'))
SETTINGS_DIR = os.path.dirname(os.environ.get('SONADOR_SITECONFIG'))

# Add lib and apps directories to the path
sys.path.insert(0, os.path.join(BASE_DIR, 'lib'))
sys.path.append(os.path.join(BASE_DIR, 'apps'))
if not SETTINGS_DIR in sys.path:
    sys.path.append(SETTINGS_DIR)

# Import guru helpers
import guru.apisettings as gapicodes
import messages.apisettings as mapicodes
import secure.apisettings as sapicodes



# Sonador Release Version

# Version of the Sonador web application (backend + bundled API). This is deliberately a source
# constant rather than a `site.config` value: it identifies the *build* that is deployed, not the
# way a particular deployment is configured, so a site operator must not be able to change it.
#
# Branch convention:
#   * `master`      -> 'dev' (unreleased; the working trunk)
#   * `dev/X.Y`     -> a semantic pre-release, bumped as the release is stabilized (e.g. '0.4.0-rc1')
#   * `release/X.Y` -> the finalized semantic version for the release (e.g. '0.4.0')
#
# Reported to the viewer through the OHIF application configuration document
# (`visionaire.views.ohif.OhifConfigView`, served at `/ohif/config`) as `sonadorVersion`, where it
# is surfaced in the viewer's Settings > About table as "Sonador API Version" so a user can
# establish which Sonador web API their frontend is talking to.
SONADOR_VERSION = '0.4.1'



# Site Configuration Settings

# Core site configuration settings
siteconfig_site = siteconfig.get('Site-Config', {})
SITE_ID = int(siteconfig_site.get('SITE_ID', 0))
SITE_NAME = siteconfig_site.get('SITE_NAME')
SITE_URL = SITE_NAME
SECRET_KEY = siteconfig_site.get('SECRET_KEY')
INTERNAL_IPS = tuple(siteconfig_site.get('INTERNAL_IPS', ('127.0.0.1',) ))
VERIFY_SSL_CONNECTIONS = config_str2bool(siteconfig_site.get('VERIFY_SSL_CONNECTIONS', True))

# Support multi-line strings in the application configuration for ALLOWED_HOSTS.
# This works around a limitation in ArgoCD and Helm which will split lines in
# config maps at 80 characters. When using multi-line allowed hosts in a site config,
# they should be enclosed in triple quotes, with a comma at the end of the line.
# Tabs may be used for readability.
if isinstance(siteconfig_site.get('ALLOWED_HOSTS'), six.text_type):
    ALLOWED_HOSTS_STR = siteconfig_site.get('ALLOWED_HOSTS')
    ALLOWED_HOSTS = tuple([s.replace("'", '').replace('"', '').strip() for s in ALLOWED_HOSTS_STR.replace('\n', '').replace('\t', '').split(',')])
else: ALLOWED_HOSTS = tuple(siteconfig_site.get('ALLOWED_HOSTS', []))


# Remote Request Settings
HTTP_REQUEST_TIMEOUT_DEFAULT = siteconfig_site.get(
    'HTTP_REQUEST_TIMEOUT_DEFAULT', gapicodes.HTTP_REQUEST_TIMEOUT_DEFAULT)



# Logging
LOG_LEVEL = siteconfig_site.get('LOG_LEVEL', mapicodes.API_LOG_INFO.upper())
LOG_LEVEL_CONSOLE = LOG_LEVEL
LOG_FILE = siteconfig_site.get('LOG_FILE')


MANAGEMENT_LOG_FORMAT = siteconfig_site.get('MANAGEMENT_LOG_FORMAT', gapicodes.MANAGEMENT_LOG_FORMAT)
APPLICATION_LOG_FORMAT = siteconfig_site.get('APPLICATION_LOG_FORMAT', gapicodes.APPLICATION_LOG_FORMAT)

siteconfig_logging = siteconfig.get('Logging', {})

LOG_CONFIG_HANDLERS = siteconfig_logging.get('Handlers', {})
LOG_CONFIG_LOGGERS = siteconfig_logging.get('Loggers', {})

if not isinstance(LOG_CONFIG_HANDLERS, dict):
    raise TypeError('Invalid logging handlers configuration (type: %s): %r'
        % (str(type(LOG_CONFIG_HANDLERS)), LOG_CONFIG_HANDLERS))
if not isinstance(LOG_CONFIG_LOGGERS, dict):
    raise TypeError('Invalid logging loggers configuration (type: %s): %r'
        % (str(type(LOG_CONFIG_LOGGERS)), LOG_CONFIG_LOGGERS))


# Convert propagate values of Loggers to boolean
for lname, lconfig in six.iteritems(LOG_CONFIG_LOGGERS):
    lconfig['propagate'] = config_str2bool(lconfig.get('propagate'))

# Log Rotation
LOG_HISTORY_DAYS_DEFAULT = 18*30
LOG_HISTORY_DAYS = int(siteconfig_site.get('LOG_HISTORY_DAYS', LOG_HISTORY_DAYS_DEFAULT))



# Database Settings
DATABASES = siteconfig.get('Databases', {})

for dbname, dbdata in six.iteritems(DATABASES):

        # Set CONN_MAX_AGE type for database entries
        if dbdata.get('CONN_MAX_AGE') and not isinstance(dbdata.get('CONN_MAX_AGE'), int):
                try: dbdata['CONN_MAX_AGE'] = int(dbdata.get('CONN_MAX_AGE'))
                except Exception as err:
                    raise ValueError('Invalid CONN_MAX_AGE value: %r' % dbdata.get('CONN_MAX_AGE'))


# Database Migrations
MIGRATION_MODULES = siteconfig.get('Database-Migrations', {})


# Database Routers (Production)
DATABASE_ROUTERS = siteconfig_site.get('DATABASE_ROUTERS', [])



# Site Connection Settings
siteconfig_connection = siteconfig.get('Site-Connection', {})
SITE_CONNECT_SCHEME = siteconfig_connection.get('SITE_CONNECT_SCHEME')
SITE_CONNECT_PORT = siteconfig_connection.get('SITE_CONNECT_PORT')
SITE_CONNECT_SCHEME_DEVEL = siteconfig_connection.get('SITE_CONNECT_SCHEME_DEVEL')
SITE_CONNECT_PORT_DEVEL = siteconfig_connection.get('SITE_CONNECT_PORT_DEVEL')
SITE_CONNECT_MATCH_SITE_SCHEME = config_str2bool(
    siteconfig_connection.get('SITE_CONNECT_MATCH_SITE_SCHEME'))
SITE_CONNECT_MATCH_SITE_NETLOC = config_str2bool(
    siteconfig_connection.get('SITE_CONNECT_MATCH_SITE_NETLOC'))
BASE_URL = siteconfig_connection.get('BASE_URL')



# Runtime settings
DEBUG = True
template_debug = DEBUG




# Timezone and Language Settings

# Enable time zone support for forms and templates
# Database values are stored in UTC
siteconfig_locale = siteconfig.get('Localization', {})
USE_TZ = True

# Use UTC timezone by default
TIME_ZONE = siteconfig_locale.get('TIME_ZONE', 'UTC')

# Language Settings
LANGUAGE_CODE = siteconfig_locale.get('LANGUAGE_CODE', 'en-us')
MACHINE_DEFAULT_LANGUAGE_ABBR = siteconfig_locale.get('MACHINE_DEFAULT_LANGUAGE_ABBR', 'en')
MACHINE_DEFAULT_LANGUAGE_TERRITORY_ABBR = siteconfig_locale.get('MACHINE_DEFAULT_LANGUAGE_TERRITORY_ABBR', 'US')
LANGUAGES = (
    ('en', 'English'),
)
USE_I18N = True



# Application definition

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres.search',
    'corsheaders',

    # Oak-Tree Base Applications
    'guru',             # Oak-Tree Base Application
    'secure',           # Secure Access API: access IDs/secret keys, access tokens
    'sassycss',         # Helper utilities for managing styles and artsy resources
    'microservices',    # Base classes for managing integration with remote systems
    'content',
    'wgtauth',          # oAuth2 authentication
    'wgtauth.social.app.WagtailAuthAppConfig',
    'wgtauth.registration.app.WagtailRegistrationAppConfig',

    # Sonador Admin
    'core.apps.SonadorAdminConfig',

    # Sonador
    'visionaire.app.VisionaireAppConfig',
    'gateway.app.ClinicalGatewayAppConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
]

ROOT_URLCONF = 'sonador.urls'


sonador_template_context_processors = [
    'django.template.context_processors.debug',
    'django.template.context_processors.request',
    'django.contrib.auth.context_processors.auth',
    'django.contrib.messages.context_processors.messages',
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(PROJECT_CONFIGURATION_ROOT, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': sonador_template_context_processors,
        },
    },
]

WSGI_APPLICATION = 'sonador.wsgi.application'


# SCSS Resource Paths
SCSS_RESOURCE_PATHS = (
    os.path.join(PROJECT_ROOT, 'lib', 'guru', 'styles'),
    os.path.join(PROJECT_ROOT, 'lib', 'content', 'styles'),
)
SCSS_STATIC_ROOT = os.path.join(PROJECT_CONFIGURATION_ROOT, 'static', 'css')
if not os.path.exists(SCSS_STATIC_ROOT):
    os.makedirs(SCSS_STATIC_ROOT)



# Password validation
# https://docs.djangoproject.com/en/2.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

STATICFILES_DIRS = [
    os.path.join(PROJECT_CONFIGURATION_ROOT, 'static'),
]

STATIC_URL = '/static/'


# Authentication Settings
siteconfig_auth = siteconfig.get('Authentication', {})

# In version 0.1 of Sonador, it was possible to turn off authentication. Since version 0.2 
# authentication is always enabled.
AUTH_ENABLED = True
SERVER_APITOKEN = siteconfig_auth.get('SERVER_APITOKEN')
if AUTH_ENABLED and not SERVER_APITOKEN:
    raise ValueError('Authentication enabled for the server, but no API server token provided')

SECURE_API_ACCESSID_ENABLED = AUTH_ENABLED
SECURE_API_APITOKEN_ENABLED = AUTH_ENABLED

AUTH_EXPIRES_IN_DEFAULT = int(siteconfig_auth.get('AUTH_EXPIRES_IN_DEFAULT', 30))
AUTH_EXPIRES_IN_SERVERTOKEN = int(siteconfig_auth.get('AUTH_EXPIRES_IN_SERVERTOKEN', AUTH_EXPIRES_IN_DEFAULT))
AUTH_EXPIRES_IN_APITOKEN = int(siteconfig_auth.get('AUTH_EXPIRES_IN_APITOKEN', AUTH_EXPIRES_IN_DEFAULT))
AUTH_EXPIRES_IN_SESSION = int(siteconfig_auth.get('AUTH_EXPIRES_IN_SESSION', AUTH_EXPIRES_IN_DEFAULT))
AUTH_EXPIRES_IN_ORTHANC_PASSWORD = int(siteconfig_auth.get('AUTH_EXPIRES_IN_ORTHANC_PASSWORD', AUTH_EXPIRES_IN_DEFAULT))

# Sonador Credentials Cache
AUTH_CREDENTIALS_CACHE = config_str2bool(siteconfig_auth.get('AUTH_CREDENTIALS_CACHE', False))
AUTH_CREDENTIALS_CACHE_MAX_AGE = int(siteconfig_auth.get('AUTH_CREDENTIALS_CACHE_MAX_AGE', 180))
AUTH_CREDENTIALS_CACHE_KEY_ITERATIONS = int(siteconfig_auth.get('AUTH_CREDENTIALS_CACHE_KEY_ITERATIONS', 16))
AUTH_CREDENTIALS_CACHE_SESSION_KEY_LENGTH = int(siteconfig_auth.get('AUTH_CREDENTIALS_CACHE_SESSION_KEY_LENGTH', 42))


# Site Redirect Settings
LOGIN_REDIRECT_URL = siteconfig_auth.get('LOGIN_REDIRECT_URL', '/')
LOGOUT_REDIRECT_URL = siteconfig_auth.get('LOGOUT_REDIRECT_URL', '/accounts/logout/success')


# CORS Settings
CORS_ALLOWED_ORIGINS = siteconfig_site.get('CORS_ALLOWED_ORIGINS', [])
CORS_ALLOWED_ORIGIN_REGEXES = siteconfig_site.get('CORS_ALLOWED_ORIGIN_REGEXES', [])
CORS_ALLOW_CREDENTIALS = config_str2bool(siteconfig_site.get('CORS_ALLOW_CREDENTIALS', False))
CSRF_TRUSTED_ORIGINS = siteconfig_site.get('CSRF_TRUSTED_ORIGINS', [])


# Viewer Settings
siteconfig_viewer = siteconfig.get('Viewer', {})
VIEWER_EMPTY_STATE_MESSAGE = siteconfig_viewer.get('VIEWER_EMPTY_STATE_MESSAGE',
    'Your user account is not associated with any imaging servers. Please contact your system administrator.')
VIEWER_FAREWELL_MESSAGE = siteconfig_viewer.get('VIEWER_FAREWELL_MESSAGE',
    '# Signed Out\n\nYou have been logged out of Sonador successfully. Your session has ended and '
    'the imaging data on this device is no longer accessible.')



# Django Response Cache

# `site.config` is parsed by ConfigObj, which has no type system: every scalar it reads is a
# string. Nothing downstream repairs that. Django's `PyMemcacheCache` merges `params['OPTIONS']`
# verbatim into the `pymemcache.HashClient(...)` keyword arguments, so `max_pool_size = 64`
# reaches the pool as the string `'64'` and raises deep inside the client at the first cache
# access -- long after boot, in a request, where it reads as a cache outage rather than as a
# configuration error.
#
# Booleans are the more dangerous half of the problem, because they do not raise at all: every
# non-empty string is truthy, so `no_delay = False` read literally turns the option *on*. The
# cache still works, just not the way the operator configured it. That is why the parsing below
# is strict -- an unrecognized spelling is an error rather than a silent `False`, which is the
# one thing `config_str2bool` cannot give us.
#
# This matters as of 0.4.1: the FastAPI/Uvicorn container serves Sonador from a thread pool
# under Python 3.14, and a memcached client shared across those threads needs `use_pooling` and
# `max_pool_size` to hand each thread a connection of its own. Those are precisely the options
# that have to arrive as a real bool and a real int.

# Cache backends whose `OPTIONS` are validated against `CACHE_PYMEMCACHE_OPTIONS` below. The
# table describes `pymemcache.client.hash.HashClient` keyword arguments specifically, so it is
# deliberately not applied to any other backend -- a `pylibmc`, redis, or locmem alias takes a
# different option vocabulary and its `OPTIONS` are passed through untouched.
CACHE_PYMEMCACHE_BACKENDS = (
    'django.core.cache.backends.memcached.PyMemcacheCache',
)

# `HashClient` keyword arguments that can be expressed as a `site.config` scalar, the type each
# must be handed to the client as, and the guidance shown when one is wrong. Options whose values
# are Python objects (`serde`, `serializer`, `deserializer`, `socket_module`, `socket_keepalive`,
# `tls_context`, `hasher`, `lock_generator`) cannot be written in an INI file at all and are
# absent on purpose: naming one in `site.config` is a configuration error, not an unsupported knob.
CACHE_PYMEMCACHE_OPTIONS = {

    # Concurrency. Without these a single connection is shared by every worker thread.
    'use_pooling': (bool, 'Set "use_pooling = True" so each worker thread checks out its own '
        + 'connection instead of sharing one.'),
    'max_pool_size': (int, 'Size the pool to the Uvicorn thread pool and never below it '
        + '(for example: max_pool_size = 64).'),
    'pool_idle_timeout': (float, 'Seconds an idle pooled connection is kept before it is '
        + 'discarded; 0 keeps connections forever (for example: pool_idle_timeout = 60).'),
    'no_delay': (bool, 'Set "no_delay = True" to disable Nagle buffering on the memcached '
        + 'sockets.'),

    # Socket timeouts. Unset means "block forever", which stalls a worker thread on a slow node.
    'connect_timeout': (float, 'Seconds to wait for a memcached connection, as a number '
        + '(for example: connect_timeout = 1.0).'),
    'timeout': (float, 'Seconds to wait for a memcached response, as a number '
        + '(for example: timeout = 1.0).'),

    # Failover behaviour across the nodes named in LOCATION.
    'retry_attempts': (int, 'Number of times a dead memcached node is retried before it is '
        + 'removed from the ring (for example: retry_attempts = 2).'),
    'retry_timeout': (float, 'Seconds between retries of a dead memcached node '
        + '(for example: retry_timeout = 1.0).'),
    'dead_timeout': (float, 'Seconds a memcached node stays marked dead before it is retried '
        + '(for example: dead_timeout = 60).'),
    'ignore_exc': (bool, 'Set "ignore_exc = True" to treat a memcached failure as a cache miss '
        + 'rather than raising into the request.'),

    # Protocol and key handling.
    'default_noreply': (bool, 'Set "default_noreply = False" to wait for memcached to acknowledge '
        + 'writes. Django sets this itself; override it only deliberately.'),
    'allow_unicode_keys': (bool, 'Set "allow_unicode_keys = True" to permit non-ASCII cache keys. '
        + 'Django sets this itself; override it only deliberately.'),
    'key_prefix': (bytes, 'A string prefixed to every key sent to memcached, used to separate '
        + 'tenants sharing one server (for example: key_prefix = sonador).'),
    'encoding': (str, 'Character encoding used for cache keys (for example: encoding = ascii).'),
}

# Options that carry a quantity, and the smallest value that is meaningful for each. A pool of
# zero connections and a zero-second socket timeout are not configurations, they are outages, so
# they are rejected here rather than at the first cache access. Options absent from this map only
# have to be non-negative; `pool_idle_timeout = 0` and `retry_attempts = 0` are both legitimate.
CACHE_PYMEMCACHE_OPTION_MINIMUMS = {
    'max_pool_size': 1,
    'connect_timeout': 1e-3,
    'timeout': 1e-3,
}

# Recognized spellings of a false boolean, mirroring `CONFIG_POSITIVE`.
CONFIG_NEGATIVE = ('false', 'no', 'negative', 'nope', 'n', '0', 'f')


def config_cache_scalar(value, expected):
    ''' Coerce a single `site.config` scalar to `expected`, raising `ValueError` with a
        description of the problem -- not of its location, which the caller adds.

        This is intentionally stricter than `config_str2bool`: an unrecognized boolean is an
        error rather than a `False`, so that "no_delay = Flase" cannot quietly enable the
        option it was written to disable.
    '''
    if expected is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, six.string_types):
            spelling = value.strip().lower()
            if spelling in CONFIG_POSITIVE:
                return True
            if spelling in CONFIG_NEGATIVE:
                return False
        raise ValueError('expected a true/false value (accepted spellings: %s), got %r'
            % (', '.join(CONFIG_POSITIVE + CONFIG_NEGATIVE), value))

    if expected in (int, float):

        # bool is a subclass of int, so "max_pool_size = True" would otherwise be read as a
        # pool of one. The string spellings matter more than the literal: ConfigObj hands
        # everything over as text, so "True" is what a confused site config actually contains.
        if isinstance(value, bool) or (isinstance(value, six.string_types)
                and value.strip().lower() in CONFIG_POSITIVE + CONFIG_NEGATIVE
                and not value.strip().isdigit()):
            raise ValueError('expected a number, got the boolean %r' % (value,))

        try:
            return int(value) if expected is int else float(value)
        except (TypeError, ValueError):
            raise ValueError('expected a %s, got %r'
                % ('whole number' if expected is int else 'number', value))

    if expected is bytes:
        # pymemcache concatenates `key_prefix` with already-encoded keys, so it has to be bytes.
        if isinstance(value, bytes):
            return value
        if isinstance(value, six.string_types):
            try:
                return value.encode('ascii')
            except UnicodeEncodeError:
                raise ValueError('expected plain ASCII text, got %r' % (value,))
        raise ValueError('expected text, got %r' % (value,))

    if not isinstance(value, six.string_types):
        raise ValueError('expected text, got %r' % (value,))
    return value


def coerce_cache_options(alias, options):
    ''' Validate and type-coerce the `OPTIONS` of one pymemcache cache alias, returning a new
        dict. Unrecognized option names are rejected here rather than allowed to reach
        `HashClient`, where they surface as an opaque `TypeError` on the first cache access.
    '''
    location = '[Cache][[CACHES]][[[%s]]][[[[OPTIONS]]]]' % alias
    coerced = {}

    for name, value in options.items():

        if name not in CACHE_PYMEMCACHE_OPTIONS:
            raise ValueError('Unrecognized memcached option "%s" in %s. pymemcache accepts '
                % (name, location)
                + 'the following options from a site config: %s.'
                % ', '.join(sorted(CACHE_PYMEMCACHE_OPTIONS)))

        expected, guidance = CACHE_PYMEMCACHE_OPTIONS[name]

        if isinstance(value, (dict, list, tuple)):
            raise ValueError('Invalid value for "%s" in %s: expected a single value, got %r. '
                % (name, location, value)
                + guidance)

        try:
            coerced[name] = config_cache_scalar(value, expected)
        except ValueError as err:
            raise ValueError('Invalid value for "%s" in %s: %s. %s'
                % (name, location, err, guidance))

        if expected in (int, float):
            minimum = CACHE_PYMEMCACHE_OPTION_MINIMUMS.get(name, 0)
            if coerced[name] < minimum:
                raise ValueError('Invalid value for "%s" in %s: %r is below the smallest '
                    % (name, location, value)
                    + 'usable value (%s). %s' % (minimum, guidance))

    # A pool size with pooling switched off is the failure this validation exists to catch: it
    # parses, it boots, and every worker thread still shares one connection. It is a warning
    # rather than an error because the combination is a valid way to disable pooling temporarily.
    if 'max_pool_size' in coerced and not coerced.get('use_pooling', False):
        warnings.warn('%s sets "max_pool_size" but leaves "use_pooling" off, so connection '
            % location
            + 'pooling is disabled and every worker thread will share a single memcached '
            + 'connection. Set "use_pooling = True" to size the pool.')

    return coerced


def coerce_cache_config(caches):
    ''' Validate a `CACHES` mapping read from `site.config` and return an equivalent mapping
        with its values coerced to the types Django and pymemcache require.

        A misconfigured cache must fail at boot rather than at the first request: an operator
        reading a stack trace out of a live worker has no way to tell a bad option value from a
        memcached node that has gone away.
    '''
    coerced = {}

    for alias, cache in caches.items():

        if not isinstance(cache, dict):
            raise TypeError('Invalid cache configuration for "%s" (type: %s): %r. Each cache '
                % (alias, str(type(cache)), cache)
                + 'must be a [[[section]]] under [Cache][[CACHES]].')

        cache = dict(cache)
        backend = cache.get('BACKEND')
        if not backend:
            raise ValueError('No BACKEND configured for the "%s" cache. Set BACKEND in '
                % alias
                + '[Cache][[CACHES]][[[%s]]], for example: BACKEND = %s'
                % (alias, CACHE_PYMEMCACHE_BACKENDS[0]))

        # TIMEOUT is the default expiry in seconds. Django coerces it with a bare `int()` and
        # silently substitutes 300 when that fails, so a typo here yields a cache that works
        # with the wrong lifetime -- the failure is invisible unless it is caught at boot.
        if 'TIMEOUT' in cache:
            timeout = cache['TIMEOUT']
            if timeout is None or (isinstance(timeout, six.string_types)
                    and timeout.strip().lower() in ('', 'none')):
                # Django reads None as "cache entries never expire".
                cache['TIMEOUT'] = None
            else:
                try:
                    cache['TIMEOUT'] = config_cache_scalar(timeout, int)
                except ValueError as err:
                    raise ValueError('Invalid TIMEOUT for the "%s" cache: %s. TIMEOUT is the '
                        % (alias, err)
                        + 'default entry lifetime in seconds; use "None" for entries that never '
                        + 'expire (for example: TIMEOUT = 300).')

                if cache['TIMEOUT'] < 0:
                    raise ValueError('Invalid TIMEOUT for the "%s" cache: %r is negative. Use 0 '
                        % (alias, timeout)
                        + 'to disable caching or "None" for entries that never expire.')

        # VERSION prefixes every key. Django does not coerce it at all, so a string version
        # poisons key generation and cache.incr_version() fails on a str/int comparison.
        if 'VERSION' in cache:
            try:
                cache['VERSION'] = config_cache_scalar(cache['VERSION'], int)
            except ValueError as err:
                raise ValueError('Invalid VERSION for the "%s" cache: %s. VERSION is the whole '
                    % (alias, err)
                    + 'number prefixed to every cache key (for example: VERSION = 1).')

        options = cache.get('OPTIONS') or {}
        if options and not isinstance(options, dict):
            raise TypeError('Invalid OPTIONS for the "%s" cache (type: %s): %r. OPTIONS must be '
                % (alias, str(type(options)), options)
                + 'a [[[[OPTIONS]]]] sub-section.')

        if backend in CACHE_PYMEMCACHE_BACKENDS:

            if not cache.get('LOCATION'):
                raise ValueError('No LOCATION configured for the "%s" memcached cache. Set '
                    % alias
                    + 'LOCATION in [Cache][[CACHES]][[[%s]]] to the memcached host(s), for '
                    % alias
                    + 'example: LOCATION = memcached-0:11211, memcached-1:11211')

            # An absent or empty OPTIONS section is a valid configuration -- pymemcache's own
            # defaults apply -- so there is nothing to coerce and nothing to complain about.
            if options:
                cache['OPTIONS'] = coerce_cache_options(alias, options)

        coerced[alias] = cache

    return coerced


siteconfig_cache = siteconfig.get('Cache', {})
CACHE_ENABLED = config_str2bool(siteconfig_cache.get('CACHE_ENABLED', False))
if CACHE_ENABLED:
    CACHES = siteconfig_cache.get('CACHES', {})
    if not CACHES:
        raise ValueError('The Sonador cache backend is enabled, but no cache instances are configured.')

    CACHES = coerce_cache_config(CACHES)


# HIPAA Audit Logging / Kafka Export
#
# `AUDIT_LOGGING_ENABLED` is the master switch for the audit trail. When it is off --
# the default -- no producer is constructed and no Kafka library call is made at runtime.
#
# The `[[Connection]]` sub-section is handed to `confluent_kafka.Producer(...)` with its
# keys unchanged, so it accepts any librdkafka client property verbatim (security.protocol,
# ssl.*, sasl.*). TLS and SASL are therefore a configuration concern, not a code change.
# Unknown property names are rejected by librdkafka when the producer is constructed.
siteconfig_kafka = siteconfig.get('Kafka', {})
AUDIT_LOGGING_ENABLED = config_str2bool(siteconfig_kafka.get('AUDIT_LOGGING_ENABLED', False))

siteconfig_kafka_audit = siteconfig_kafka.get('Audit', {})
AUDIT_TOPIC = siteconfig_kafka_audit.get('AUDIT_TOPIC', 'sonador-audit-event')
AUDIT_SOURCE_SITE = siteconfig_kafka_audit.get('AUDIT_SOURCE_SITE', 'sonador')

KAFKA_CONNECTION = siteconfig_kafka.get('Connection', {})
if AUDIT_LOGGING_ENABLED:

    # A misconfigured audit trail must fail at boot rather than silently record nothing:
    # the value of the feature is that the record is complete.
    if not isinstance(KAFKA_CONNECTION, dict):
        raise TypeError('Invalid Kafka connection configuration (type: %s): %r'
            % (str(type(KAFKA_CONNECTION)), KAFKA_CONNECTION))

    if not KAFKA_CONNECTION.get('bootstrap.servers'):
        raise ValueError('HIPAA audit logging is enabled, but no Kafka brokers are configured. '
            + 'Set "bootstrap.servers" in the [Kafka][[Connection]] section of the site config.')

    if not AUDIT_TOPIC:
        raise ValueError('HIPAA audit logging is enabled, but no audit topic is configured. '
            + 'Set "AUDIT_TOPIC" in the [Kafka][[Audit]] section of the site config.')
