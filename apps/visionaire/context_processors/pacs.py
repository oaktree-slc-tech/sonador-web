import posixpath

from guru.helpers import gsetting
from guru.helpers.utils.object import pick

from ..models import PacsImagingServer


def pacs_serverid(server_name):
	'''	Create an OHIF save identifier for the server from the name.

		1. Convert the server name to lowercase
		2. Convert spaces to underscores
	'''
	return server_name.lower().replace(' ', '_')


def pacs_server_dicomweb(request):
	'''	Add PACS server connection information to the request context
	'''
	return {
		'pacs_server': [s.ohif_json for s in PacsImagingServer.objects.filter(active=True)]
	} 
