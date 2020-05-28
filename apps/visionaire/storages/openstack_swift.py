from guru.helpers import gsetting

from largefiles.storages.openstack_swift import OpenStackSwiftStorage, \
	OPENSTACK_SWIFT_CONTAINER_GLOBAL_READ_PERMISSIONS


class OpenStackSwiftStaticFilesStorage(OpenStackSwiftStorage):
	'''	Storage provider which can be used for Sonador static files
	'''
	container = 'static'
	container_headers = OPENSTACK_SWIFT_CONTAINER_GLOBAL_READ_PERMISSIONS
	init_container_properties = True
	guess_unknown_content_types = True
	verify_file_urls = False


class OpenStackSwiftMediaFilesStorage(OpenStackSwiftStorage):
	'''	Storage provider which can be used for Mail Gorilla public media files
	'''
	container = 'media'
	container_headers = OPENSTACK_SWIFT_CONTAINER_GLOBAL_READ_PERMISSIONS
	init_container_properties = True
	guess_unknown_content_types = True
	verify_file_urls = False

