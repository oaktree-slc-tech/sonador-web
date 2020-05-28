from .base import *


# Resource directories: static and media roots
siteconfig_resourcefiles = siteconfig.get('Resource-Files', {})
STATIC_ROOT = siteconfig_resourcefiles.get('STATIC_ROOT', '')
MEDIA_ROOT = siteconfig_resourcefiles.get('MEDIA_ROOT', '')

# Ensure that the static root and media root provided in the configuration exist
if not os.path.exists(STATIC_ROOT) or not os.path.exists(MEDIA_ROOT):
	raise ValueError('Invalid static or media root. Static root: %s. Media root: %s.'
		% (STATIC_ROOT, MEDIA_ROOT))

STATIC_URL = '/static/'
MEDIA_URL = '/media/'

