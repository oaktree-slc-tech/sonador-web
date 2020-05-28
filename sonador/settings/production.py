import posixpath

from .base import *

# Object storage configuration
import largefiles.apisettings as ofapicodes

siteconfig_storage = siteconfig.get('Storage', {})
siteconfig_storage_type = siteconfig_storage.get('OBJECT_STORAGE_TYPE')

if not siteconfig_storage_type in (ofapicodes.API_OBJECT_STORAGE_SUPPORTED, ofapicodes.API_OBJECT_STORAGE_S3_MINIO):
	raise ValueError('Unsupported object storage type: %r' % siteconfig_storage_type)

OBJECT_STORAGE_ENABLED = True
OBJECT_STORAGE_TYPE = siteconfig_storage_type

# Amazon S3 Storage Configuration
if siteconfig_storage_type in (ofapicodes.API_OBJECT_STORAGE_S3, ofapicodes.API_OBJECT_STORAGE_S3_MINIO):

	siteconfig_s3 = siteconfig.get('S3', {})
	AWS_S3_SERVICE_URL = siteconfig_s3.get(ofapicodes.AWS_S3_SERVICE_URL_DEFAULT)
	AWS_S3_ACCESS_ID = siteconfig_s3.get(ofapicodes.AWS_S3_ACCESS_ID_DEFAULT)
	AWS_S3_SECRET_KEY = siteconfig_s3.get(ofapicodes.AWS_S3_SECRET_KEY_DEFAULT)
	AWS_S3_REGION = siteconfig_s3.get(ofapicodes.AWS_S3_REGION_DEFAULT)
	AWS_S3_SECURITY_TOKEN = siteconfig_s3.get(ofapicodes.AWS_S3_SECURITY_TOKEN_DEFAULT)

	# S3 Containers: Default, Static, Media
	AWS_S3_CONTAINER = siteconfig_s3.get(ofapicodes.AWS_S3_CONTAINER_DEFAULT)
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
	if not AWS_S3_CONTAINER:
		raise ValueError('Invalid default S3 container: %r' % AWS_S3_CONTAINER)
	if not AWS_S3_STATIC_CONTAINER:
		raise ValueError('Invalid static S3 container: %r' % AWS_S3_STATIC_CONTAINER)
	if not AWS_S3_MEDIA_CONTAINER:
		raise ValueError('Invalid media S3 container: %r' % AWS_S3_MEDIA_CONTAINER)

	STATICFILES_STORAGE = 'visionaire.storages.s3.SonadorS3StaticFilesStorage'
	DEFAULT_FILE_STORAGE = 'visionaire.storages.s3.SonadorS3MediaFilesStorage'

	STATIC_URL = posixpath.join(AWS_S3_SERVICE_URL, AWS_S3_STATIC_CONTAINER, '')
	MEDIA_URL = posixpath.join(AWS_S3_SERVICE_URL, AWS_S3_MEDIA_CONTAINER, '')

# OpenStack Swift Storage Configuration
elif siteconfig_storage_type == ofapicodes.API_OBJECT_STORAGE_SWIFT:

	siteconfig_openstack_swift = siteconfig.get('OpenStack-Swift', {})
	SWIFT_AUTH_URL = siteconfig_openstack_swift.get('SWIFT_AUTH_URL')
	SWIFT_AUTH_VERSION = siteconfig_openstack_swift.get('SWIFT_AUTH_VERSION')
	SWIFT_TENANT = siteconfig_openstack_swift.get('SWIFT_TENANT') or siteconfig_openstack_swift.get('SWIFT_PROJECT')
	SWIFT_PROJECT = siteconfig_openstack_swift.get('SWIFT_PROJECT') or SWIFT_TENANT
	SWIFT_PROJECT_DOMAIN = siteconfig_openstack_swift.get('SWIFT_PROJECT_DOMAIN')
	SWIFT_USERNAME = siteconfig_openstack_swift.get('SWIFT_USERNAME')
	SWIFT_USER_DOMAIN = siteconfig_openstack_swift.get('SWIFT_USER_DOMAIN')
	SWIFT_KEY = siteconfig_openstack_swift.get('SWIFT_KEY') or siteconfig_openstack_swift.get('SWIFT_PASSWORD')
	SWIFT_SIGNING_KEY = siteconfig_openstack_swift.get('SWIFT_SIGNING_KEY')
	SWIFT_DEFAULT_CONTAINER = siteconfig_openstack_swift.get('SWIFT_DEFAULT_CONTAINER')
	SWIFT_ENDPOINT_URL = siteconfig_openstack_swift.get('SWIFT_ENDPOINT_URL')
	_SWIFT_AUTH_VERSION = float(SWIFT_AUTH_VERSION)

	# Verify Swift 2.0 Configuration
	if 2.0 <= _SWIFT_AUTH_VERSION <= 3.0:
		if not SWIFT_TENANT:
			raise ValueError(
				'Invalid tenant %r. For installations using OpenStack Swift auth version %s, a valid tenant must be provided.'
				% (SWIFT_TENANT, SWIFT_AUTH_VERSION))
	elif 3.0 <= _SWIFT_AUTH_VERSION:
		if not SWIFT_USER_DOMAIN:
			raise ValueError((
			 	'Invalid user domain %r. For installations using OpenStack Swift auth version %s, the OpenStack user domain must '
		 		+ 'be specified.') % (SWIFT_USER_DOMAIN, SWIFT_AUTH_VERSION))
		if not SWIFT_PROJECT:
			raise ValueError(
				'Invalid project %r. For installations using OpenStack Swift auth version %s, the OpenStack project must be specified'
				% (SWIFT_PROJECT, SWIFT_AUTH_VERSION))
		if not SWIFT_PROJECT_DOMAIN:
			raise ValueError((
			 	'Invalid project domain %r. For installations using OpenStack Swift auth version %s, the OpenStack project domain '
			 	+ 'must be specified') % (SWIFT_PROJECT_DOMAIN, SWIFT_AUTH_VERSION))

	# Application storage provider
	DEFAULT_FILE_STORAGE = 'visionaire.storages.openstack_swift.OpenStackSwiftMediaFilesStorage'
	STATICFILES_STORAGE = 'visionaire.storages.openstack_swift.OpenStackSwiftStaticFilesStorage'
