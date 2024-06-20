'''	Classes and methods to verify access to Orthanc resources
'''

import guru.apisettings as gapicodes
from .. import apisettings as orthanc_api


class ServerAuthorization:
	'''	Helper class which can be used to assess Sonador server permissions.
	'''
	def __init__(self, query=None, upload=None, **kwargs):
		self.query = query
		self.upload = upload

	def acl_scoped_resource(self, resource, method):
		'''	Determine if the requested resource matches a scoped resource within Orthanc.

			* /cache/dcm-tags: dictionary of tags stored by the Sonador resource cache
			* /tools/secure-find: scoped search endpoint
			* /dicom-web/studies:  scoped DICOMweb query endpoint
		'''
		# Server DICOM tags
		if method.lower() == gapicodes.HTTP_GET.lower() and resource == orthanc_api.ORTHANC_CACHE_TAGS:			
			return True

		# DICOMmweb study endpoint (ACL mediated)
		elif method.lower() == gapicodes.HTTP_GET.lower() and resource == orthanc_api.ORTHANC_DICOMWEB_STUDIES:
			return True

		# tools/secure-find (ACL mediated)
		elif method.lower() == gapicodes.HTTP_POST.lower() and resource == orthanc_api.ORTHANC_TOOLS_FIND_SECURE:
			return True

		# DICOMweb worklist study query endpoint (ACL mediated)
		elif method.lower() == gapicodes.HTTP_GET.lower() and resource == orthanc_api.ORTHANC_DICOMWEB_WORKLIST_STUDY_QUERY:
			return True

		return None

	def query_perm(self, resource, method):
		'''	Determine if the requested resource matches a query query endpoint and return the permission
			for the server. If the request does not match a query endpoint, the method returns None.

			@returns bool or None if the method was unable to match the resource request
		'''
		# System-wide Resource Query
		if (method.lower() == gapicodes.HTTP_GET.lower() and resource == orthanc_api.ORTHANC_DICOMWEB_STUDIES) \
			or (method.lower() == gapicodes.HTTP_POST.lower() and resource in (
				orthanc_api.ORTHANC_CACHE_PATIENT, orthanc_api.ORTHANC_CACHE_STUDY, orthanc_api.ORTHANC_CACHE_SERIES)) \
			or (method.lower() == gapicodes.HTTP_POST.lower() and resource == orthanc_api.ORTHANC_TOOLS_FIND) \
			or (method.lower() == gapicodes.HTTP_GET.lower() and resource == orthanc_api.ORTHANC_DICOMWEB_SERIES) \
			or (method.lower() == gapicodes.HTTP_GET.lower() and resource in orthanc_api.ORTHANC_QUERY_RESOURCES):
			return self.query

		return None

	def upload_perm(self, resource, method):
		'''	Determine if the requested resource matches an upload endpoint and return the permission for
			the server. If the request does not match an upload endpoint, the method returns None.

			@returns bool or None if the method was unable to match the resource request
		'''
		if method.lower() == gapicodes.HTTP_POST.lower() \
			and resource in (orthanc_api.ORTHANC_DICOMWEB_STUDIES, orthanc_api.ORTHANC_INSTANCES):
			return self.upload

		return None


class ResourceAuthorization:
	'''	Helper class which can be used to assess a set of Sonador permissions
		to determine if access should be granted to a resource.		
	'''
	def __init__(self, view=None, modify=None, remove=None, comment_edit=None, comment_view=None, acl=None,
			**kwargs):
		'''	Initialize permission set
		'''
		self.view = view
		self.modify = modify
		self.remove = remove
		self.comment_edit = comment_edit
		self.comment_view = comment_view
		self.acl = acl

	def resource_perm(self, resource, orthanc_id, method, level, dicom_uid=None):
		'''	Evaluate the resource request and return the appropriate permision.

			@returns bool or None if the method was unable to match the resource request
		'''
		# Check system permissions
		if level == orthanc_api.ORTHANC_SYSTEM:

			# DICOMweb viewer permissions: view resources or retrieve metadata of specific studie
			if (method.lower() == gapicodes.HTTP_GET.lower() and orthanc_api.ORTHANC_DICOMWEB_STUDIES in resource) \
				or (orthanc_api.ORTHANC_WADO in resource):

				# Wado-URI or DICOMweb Study/Series Endpoint
				return self.view

			# Check view comment permissions
			elif (orthanc_api.ORTHANC_COMMENTS in resource and method.lower() == gapicodes.HTTP_GET.lower()):
				return self.comment_view

			# Check add/edit/remove permissions
			elif (orthanc_api.ORTHANC_COMMENTS in resource \
				and method.lower() in (gapicodes.HTTP_POST.lower(), gapicodes.HTTP_PUT.lower(), gapicodes.HTTP_DELETE.lower())):
				return self.comment_edit

		# Check view permissions
		elif level in orthanc_api.ORTHANC_IMAGING_RESOURCES and method.lower() == gapicodes.HTTP_GET.lower():
			return self.view

		# Check modify permissions
		elif level in orthanc_api.ORTHANC_IMAGING_RESOURCES and method.lower() in (gapicodes.HTTP_POST.lower(), gapicodes.HTTP_PUT.lower()):
			return self.modify

		# Check remove permissions
		elif level in orthanc_api.ORTHANC_IMAGING_RESOURCES and method.lower() == gapicodes.HTTP_DELETE.lower():
			return self.remove

		return None