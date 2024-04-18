import posixpath

from .apisettings import ORTHANC_STATIC_RESOURCES, ORTHANC_OHIF_ROOT, ORTHANC_OHIF_VIEWER, \
	ORTHANC_OHIF_ASSETS


def orthanc_hosted_staticfile(uri=None, method=None):
	'''	Determine if the provided resource is an Orthanc hosted static asset
	'''
	method = method or ''
	resource = uri or ''
	_,rtype = posixpath.splitext(resource)

	# Allow requests for static assets
	if rtype.replace('.', '').lower() in ORTHANC_STATIC_RESOURCES:
		return True

	# Allow requests to Orthanc OHIF plugin
	elif resource == ORTHANC_OHIF_VIEWER or resource.startswith(ORTHANC_OHIF_ASSETS):
		return True

	return False