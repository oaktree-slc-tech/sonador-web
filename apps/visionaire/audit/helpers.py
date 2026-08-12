'''	Dependency-free helpers shared by the audit package and its emit sites.

	Nothing here imports `fhir.resources` or `confluent_kafka`, so a view can import it
	without pulling either library into its module graph.
'''
from guru.helpers.utils.urls import sanitize_url_for_logging

from . import apisettings as audit_api


def sanitize_uri(uri):
	'''	Reduce a DICOMweb request URI to what may safely be recorded, and report which search
		keys it used.

		The mechanism lives in `guru.helpers.utils.urls.sanitize_url_for_logging`, because
		reducing a caller-supplied URL to a loggable form is a general concern -- any project
		recording a URL faces it. What is specific to this application, and therefore supplied
		here, is the vocabulary: which route tokens and identifier shapes make up an Orthanc
		or DICOMweb path, and which query parameters are DICOM or QIDO search keys.

		Every position in a DICOMweb request is client-supplied and can carry patient
		demographics or credentials -- the query value, the parameter name, a path parameter,
		a bare path segment, and the authority. The result is therefore built by allowlist
		rather than by trying to detect and remove sensitive content, which cannot be done
		reliably.

		The resource identifiers remain available in full on the `DicomUid` and `OrthancId`
		details, which are taken from the cleaned form rather than from the raw URI.

		@input uri (str or None)

		@returns tuple (path, query_keys)
	'''
	return sanitize_url_for_logging(uri,
		allowed_segments=audit_api.AUDIT_URI_ROUTE_TOKENS,
		segment_patterns=audit_api.AUDIT_URI_IDENTIFIER_PATTERNS,
		allowed_query_keys=audit_api.AUDIT_QUERY_KEY_ALLOWLIST,
		placeholder=audit_api.AUDIT_URI_SEGMENT_PLACEHOLDER,
		unlisted_template=audit_api.AUDIT_QUERY_KEYS_UNLISTED)


def server_audit_label(server):
	'''	Resolve the value recorded on `entity.detail.ImagingServer`.

		The rendering itself belongs to the model and lives on
		`PacsImagingServer.auditLabel`. This only resolves the three shapes an emit site can
		hold: the model, a label already rendered by an earlier request and replayed from the
		authorization response cache, or nothing at all.

		@input server (PacsImagingServer | str | None)

		@returns str or None
	'''
	if server is None:
		return None

	if isinstance(server, str):
		return server

	return getattr(server, 'auditLabel', None) or str(server)
