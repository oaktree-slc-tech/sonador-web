from .base import *
from .production import *


# Turn on debugging for Python code and templates
DEBUG = True
TEMPLATES[0]['OPTIONS']['debug'] = DEBUG


# Connection settings
SITE_CONNECT_SCHEME = SITE_CONNECT_SCHEME_DEVEL
SITE_CONNECT_PORT = SITE_CONNECT_PORT_DEVEL

# Enable CORS for all websites
CORS_ALLOW_ALL_ORIGINS = True
