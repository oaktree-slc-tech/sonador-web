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
sys.path.append(os.path.join(BASE_DIR, 'lib'))
sys.path.append(os.path.join(BASE_DIR, 'apps'))
if not SETTINGS_DIR in sys.path:
    sys.path.append(SETTINGS_DIR)

# Import guru helpers
import guru.apisettings as gapicodes
import messages.apisettings as mapicodes
import secure.apisettings as sapicodes



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
