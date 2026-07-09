import posixpath, os
from google.oauth2 import service_account

from .base import *
from .base import LOG_CONFIG_LOGGERS, LOG_CONFIG_HANDLERS, APPLICATION_LOG_FORMAT

# Object storage configuration
import largefiles.apisettings as ofapicodes

siteconfig_storage = siteconfig.get('Storage', {})
siteconfig_storage_type = siteconfig_storage.get('OBJECT_STORAGE_TYPE')
siteconfig_site = siteconfig.get('Site', {})

if not siteconfig_storage_type in ofapicodes.API_OBJECT_STORAGE_SUPPORTED + (ofapicodes.API_OBJECT_STORAGE_S3_MINIO, "GCS"):
	raise ValueError('Unsupported object storage type: %r' % siteconfig_storage_type)

OBJECT_STORAGE_ENABLED = True
OBJECT_STORAGE_TYPE = siteconfig_storage_type

X_FRAME_OPTIONS = siteconfig_site.get('X_FRAME_OPTIONS', 'SAMEORIGIN')
XS_SHARING_ALLOWED_METHODS = siteconfig_site.get('XS_SHARING_ALLOWED_METHODS', ['POST','GET','OPTIONS', 'PUT', 'DELETE'])

# Amazon S3 Storage Configuration
if siteconfig_storage_type in (ofapicodes.API_OBJECT_STORAGE_S3, ofapicodes.API_OBJECT_STORAGE_S3_MINIO):
	siteconfig_s3 = siteconfig.get('S3', {})
	AWS_S3_SERVICE_URL = siteconfig_s3.get(ofapicodes.AWS_S3_SERVICE_URL_DEFAULT)
	AWS_S3_ACCESS_ID = siteconfig_s3.get(ofapicodes.AWS_S3_ACCESS_ID_DEFAULT)
	AWS_S3_SECRET_KEY = siteconfig_s3.get(ofapicodes.AWS_S3_SECRET_KEY_DEFAULT)
	AWS_S3_REGION = siteconfig_s3.get(ofapicodes.AWS_S3_REGION_DEFAULT)
	AWS_S3_SECURITY_TOKEN = siteconfig_s3.get(ofapicodes.AWS_S3_SECURITY_TOKEN_DEFAULT)

	# S3 Containers: Default, Static, Media
	AWS_S3_STATIC_CONTAINER = siteconfig_s3.get('AWS_S3_STATIC_CONTAINER')
	AWS_S3_MEDIA_CONTAINER = siteconfig_s3.get('AWS_S3_MEDIA_CONTAINER')

	# Verify connection and access credentials
	if not AWS_S3_SERVICE_URL:
		raise ValueError('Invalid S3 service URL: %r' % AWS_S3_SERVICE_URL)
	if not AWS_S3_ACCESS_ID or not AWS_S3_SECRET_KEY:
		raise ValueError('Invalid S3 access ID or secret key: %r, %r'
						 % (AWS_S3_ACCESS_ID, AWS_S3_SECRET_KEY))
	if not AWS_S3_REGION:
		raise ValueError('Invalid S3 region: %r' % AWS_S3_REGION)

	# Verify that settings for the AWS_S3_CONTAINERS are provided
	if not AWS_S3_STATIC_CONTAINER:
		raise ValueError('Invalid static S3 container: %r' % AWS_S3_STATIC_CONTAINER)
	if not AWS_S3_MEDIA_CONTAINER:
		raise ValueError('Invalid media S3 container: %r' % AWS_S3_MEDIA_CONTAINER)

	STORAGES = {
		'default': {'BACKEND': 'visionaire.storages.s3.SonadorS3MediaFilesStorage'},
		'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
	}
	MEDIA_URL = posixpath.join(AWS_S3_SERVICE_URL, AWS_S3_MEDIA_CONTAINER, '')

elif siteconfig_storage_type == 'GCS':

	siteconfig_gcs = siteconfig.get('GCS', {})
	GS_MEDIA_BUCKET = siteconfig_gcs.get('GS_MEDIA_BUCKET')
	GS_STATIC_BUCKET = siteconfig_gcs.get('GS_STATIC_BUCKET')
	GS_PROJECTID = siteconfig_gcs.get("GS_PROJECTID")
	GS_CREDENTIALS_PATH = siteconfig_gcs.get("GS_CREDENTIALS_PATH")
	GS_DEFAULT_ACL = siteconfig_gcs.get("GS_DEFAULT_ACL", "publicRead")

	if not GS_MEDIA_BUCKET:
		raise ValueError('No Media Bucket Provided')

	if not GS_STATIC_BUCKET:
		raise ValueError('No Static Bucket Provided')


	# GS_CREDENTIALS = gsetting('GOOGLE_APPLICATION_CREDENTIALS')
	MEDIA_URL = 'https://storage.googleapis.com/{}/'.format(GS_MEDIA_BUCKET)
	STORAGES = {
		'default': {'BACKEND': 'visionaire.storages.gcp.GoogleCloudMediaStorage'},
		'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
	}


# Static files configuration: Sonador hosts complex front-end applications which
# utilize background workers and must be served from the same domain that the
# web application runs from. For a production deployment of Sonador the
# files are served by a specialized FastAPI instance deployed alongside the
# core Django app within Uvicorn.
siteconfig_static = siteconfig.get('Resource-Files')

# Ensure that the provided static root folder exists. The static root folder
# is used to aggregate all assets prior to deployment. It should be present,
# even for development deployments. (The development module from Sonador)
# consumes from this settings file.
STATIC_ROOT = siteconfig_static.get('STATIC_ROOT')
if not os.path.exists(STATIC_ROOT or ''):
	raise ValueError('Invalid static files root folder. "%s" does not exist.' % STATIC_ROOT)

# Static URL root
STATIC_URLROOT = 'static'
STATIC_URL = posixpath.join('/', STATIC_URL)



# Disable debug configuration
DEBUG = False


# Production Logging Configuration
LOGGING = {
	'version': 1,
	'disable_existing_loggers': False,
	'formatters': {
		'application': { 'format': APPLICATION_LOG_FORMAT },
	}
}


# Default developemnt logging handlers
if not LOGGING.get('handlers'):
	LOGGING_HANDLERS = LOGGING['handlers'] = {}
else: LOGGING_HANDLERS = LOGGING['handlers']

LOGGING_HANDLERS.update(LOG_CONFIG_HANDLERS or {})


# Add console handler
if not LOGGING_HANDLERS.get('console'):
	LOGGING_HANDLERS['console'] = {
		'class': 'logging.StreamHandler', 'formatter': 'application',
	}


# Root logging configuration
if not LOGGING.get('root'):
	LOGGING['root'] = {
		'handlers': ['console'],
		'level': LOG_LEVEL,
		'formatter': 'application',
	}


# Root Logger
LOGGING_LOGGERS = LOGGING['loggers'] = { '': { 'level': LOG_LEVEL, 'handlers': ['console'] }}
LOGGING_LOGGERS.update(LOG_CONFIG_LOGGERS or {})