'''	Classes and methods to verify access to Orthanc resources.
'''
import logging

import guru.apisettings as gapicodes
from .. import apisettings as orthanc_api

logger = logging.getLogger(__name__)


class ServerAuthorization:
	'''	Helper class which can be used to assess Sonador server permissions.

		* `query`: provide access to query all resources stored on the server
		* `upload`: provide access to the upload endpoint to add new data
			to the server
	'''
	def __init__(self, query=None, upload=None, **kwargs):
		self.query = query
		self.upload = upload

	def acl_scoped_resource(self, resource, method):
		'''	Determine if the requested resource matches a scoped resource within Orthanc.

			* /cache/dcm-tags (all users): dictionary of tags stored by the Sonador resource cache
			* /tools/secure-find (ACL mediated): scoped search endpoint
			* /dicom-web/studies (ACL mediated): scoped DICOMweb query endpoint
			* /tools/bulk-content (ACL mediated): scoped by filter endpoint
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

		# tools/bulk-content (ACL mediated)
		elif method.lower() == gapicodes.HTTP_POST.lower() and resource == orthanc_api.ORTHANC_TOOLS_BULK_CONTENT:
			return True

		# DICOMweb worklist study query endpoint (ACL mediated)
		elif method.lower() == gapicodes.HTTP_GET.lower() and resource == orthanc_api.ORTHANC_DICOMWEB_WORKLIST_STUDY_QUERY:
			return True

		# Orthanc System Endpoint: deployment details needed for config/frontend
		elif method.lower() == gapicodes.HTTP_GET.lower() and resource == orthanc_api.ORTHANC_SYSTEM_ENDPOINT:
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
	
		* `view`: retrieve pixel/binary data for the resource
		* `modify`: modify meta or binary data
		* `remove`: delete the resource from the server
		* `comment_edit`: edit/modify comments for the resource. When `comment_edit` is True,
			users are also able to view other comments, regardless of the value of `comment_view`.
		* `comment_view`: view (but not modify) comments
		* `acl`: manage ACL permissions for the resource
		* `worklist`: create and access worklists
	'''
	def __init__(self, view=None, modify=None, remove=None, comment_edit=None, comment_view=None, acl=None,
			worklist=None, modify_traverse=None, remove_traverse=None, **kwargs):
		'''	Initialize permission set

			`modify_traverse`/`remove_traverse` are ancestor-traversal signals supplied by the
			local-ACL policy builder (orthanc-sonador). The authorization plugin explodes a leaf
			modify/remove request into the full patient -> study -> series hierarchy and requires
			every level to be granted with the same method; under IncludeResourceUri only the leaf
			carries a non-empty resource. These flags let an ancestor (empty-resource) POST/PUT or
			DELETE pass for the sake of resolving the hierarchy to the leaf, WITHOUT granting the
			real `modify`/`remove` permission on the ancestor itself (the leaf still enforces those).
		'''
		self.view = view
		self.modify = modify
		self.remove = remove
		self.comment_edit = comment_edit
		self.comment_view = comment_view
		self.acl = acl
		self.worklist = worklist

		# Ancestor-traversal signals. When the policy builder does not supply an explicit value
		# (e.g. the GLOBAL/pattern policy, which grants its permission uniformly at every matched
		# level), traversal permission defaults to the real permission so global modify/remove still
		# authorizes ancestor levels.  The LOCAL policy builder always supplies an explicit bool,
		# which overrides this default (including an explicit False) so a descendant-only grant does
		# not leak modify/remove onto its ancestors.
		self.modify_traverse = modify if modify_traverse is None else modify_traverse
		self.remove_traverse = remove if remove_traverse is None else remove_traverse

	def resource_perm(self, resource, orthanc_id, method, level, dicom_uid=None, action=None):
		'''	Evaluate the resource request and return the appropriate permision.

			`action` is a bounded, closed-enum operation token (e.g. "comment") emitted by the
			Orthanc auth plugin's trusted route parser and applied to EVERY level of the resource
			hierarchy.  It lets us evaluate a meaningful permission at each level of a sub-resource
			request instead of falling back to a broad "modify" check on the ancestors (which would
			deny the whole request, since the plugin requires every level to be granted).

			@returns bool or None if the method was unable to match the resource request
		'''
		# Check system permissions
		if level == orthanc_api.ORTHANC_SYSTEM:

			# DICOMweb viewer permissions: view resources or retrieve metadata of specific studies
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

		# Check worklist permission: require worklist and view. Worklist provides permission to interact with 
		# worklist endpoint and view providers permission to interact with the resource.
		elif orthanc_api.ORTHANC_RESOURCE_WORKLIST in resource:
			return self.worklist and self.view

		# Comment sub-resource requests (e.g. POST /series/<id>/comments).
		#
		# The auth plugin explodes such a request into the full resource hierarchy
		# (patient -> study -> series) and requires EVERY level to be granted.  It tags
		# every level with action="comment"; the leaf (the resource the comment actually
		# lives on) additionally carries a non-empty `resource`/uri (this requires the
		# plugin's "IncludeResourceUri" option, which is what distinguishes the leaf from
		# its ancestors here), while the ancestors carry an empty `resource`.
		#
		# To satisfy the all-levels-must-pass rule without escalating ancestor access, we
		# require the comment permission on the leaf and ordinary `view` on the ancestors:
		# reading comments needs comment_view on the leaf, writing needs comment_edit.
		elif level in orthanc_api.ORTHANC_IMAGING_RESOURCES and action == orthanc_api.ORTHANC_ACTION_COMMENT:

			# Ancestor levels only need read access so the hierarchy can resolve
			if not resource:
				return self.view

			# Leaf level: read comments with comment_view, write them with comment_edit
			if method.lower() == gapicodes.HTTP_GET.lower():
				return self.comment_view

			return self.comment_edit

		# Check view permissions
		elif level in orthanc_api.ORTHANC_IMAGING_RESOURCES and method.lower() == gapicodes.HTTP_GET.lower():

			# DICOMweb comment reads arrive here with action="" (the plugin tags them as a
			# "system" access with no action; clean_auth_request() re-derives the level to the
			# imaging resource but cannot back-fill the action).  The standard-API comment read
			# is handled by the action branch above; this mirrors comment_view enforcement for
			# the DICOMweb route so a plain `view` grant cannot read comments.
			if resource and orthanc_api.ORTHANC_COMMENTS in resource:
				return self.comment_view

			return self.view

		# Check modify permissions for resource type:
		# 1. POST request for patient, series, or study
		# 2. POST request for study worklist
		elif level in orthanc_api.ORTHANC_IMAGING_RESOURCES and method.lower() in (gapicodes.HTTP_POST.lower(), gapicodes.HTTP_PUT.lower()):

			# Ancestor levels are granted via the modify-traverse signal, NOT a blanket view.
			#
			# The auth plugin explodes a sub-resource request into the full hierarchy
			# (patient -> study -> series) and requires EVERY level to be granted with the
			# same method.  With the plugin's "IncludeResourceUri" option enabled, ONLY the
			# leaf carries a non-empty `resource`/uri; the ancestors arrive with an empty
			# `resource`.  A local Modify grant on the leaf does not propagate up the
			# hierarchy.  Rather than granting `view` to ANY empty-resource POST/PUT (which also
			# matched worklist-creation ancestors, letting a user without Modify create worklist
			# items), the policy builder emits a separate `modify_traverse` flag that is True only
			# when a descendant Modify grant (or the worklist exemption) justifies traversing this
			# ancestor.  The leaf still enforces the real `modify` permission below, so this does
			# not grant direct modify on the ancestor.  Depends on IncludeResourceUri (otherwise
			# the leaf would also arrive with an empty resource).
			if not resource:
				return self.modify_traverse

			# Check for comment requsts
			if resource and orthanc_api.ORTHANC_COMMENTS in resource:
				return self.comment_edit

			return self.modify

		# Check remove permissions
		elif level in orthanc_api.ORTHANC_IMAGING_RESOURCES and method.lower() == gapicodes.HTTP_DELETE.lower():

			# Ancestor levels are granted via the remove-traverse signal, NOT a blanket view.  As
			# with the modify branch above, the plugin explodes a DELETE into the full hierarchy and
			# requires every level; only the leaf carries a non-empty `resource` (under
			# IncludeResourceUri).  A local Remove grant on the leaf does not propagate up, so the
			# policy builder emits `remove_traverse`, True only when a descendant Remove grant
			# justifies traversing this ancestor.  The leaf still enforces the real `remove`
			# permission below, so this does not grant direct remove on the ancestor.
			if not resource:
				return self.remove_traverse

			# Comment deletes are an edit of the comment, not a delete of the resource.
			# The standard API arrives here with action="comment" (handled above), but the
			# DICOMweb comment item route (/dicom-web/<type>/<uid>/comments/<id>) is sent by
			# the plugin as a "system" access with no action; Sonador re-derives its level to
			# the imaging resource in clean_auth_request() but cannot back-fill the action.
			# Mirror the POST/PUT comment handling so a comment delete maps to comment_edit
			# instead of falling through to the resource-level remove permission.
			if resource and orthanc_api.ORTHANC_COMMENTS in resource:
				return self.comment_edit

			return self.remove

		return None