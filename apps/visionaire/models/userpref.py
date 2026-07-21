import re

from django.db import models
from django.contrib.auth.models import User


# Preference documents are keyed by "<major>.<minor>" release (AR-2) so older and
# newer viewer versions can store their keys without interfering with one another.
CURRENT_PREF_VERSION = '0.4'
LEGACY_PREF_VERSION = '0.3'

# JSON fields on UserPref which hold versioned preference documents.
PREF_FIELDS = ('viewer', 'studylist')

# A version document key, e.g. "0.4" or "10.12".
PREF_VERSION_RE = re.compile(r'^\d+\.\d+$')


class UserPref(models.Model):
    ''' Allows for the OHIF frontend application to persist user settings and preferences.

        Both `viewer` and `studylist` are versioned JSON documents keyed by
        "<major>.<minor>" (AR-2). `viewer` nests per-section keys (`general`,
        `hotkeys`, `windowLevel`, `viewerMetadata`); `studylist` nests per-interface
        keys (`worklist`, `allStudies`, `shared`, `upload`). Sections are keys inside
        the documents, not columns, so new sections require no schema migration (AR-1).
    '''
    uid = models.BigAutoField(primary_key=True, unique=True, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    viewer = models.JSONField(null=True, blank=True)
    studylist = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"Entry {self.uid} : {self.user}"

    # -- Section helpers (§5.3 item 1) -------------------------------------------------

    def _document(self, field):
        ''' Return the versioned document stored in `field`, always as a dict.

            @input field (str): One of PREF_FIELDS (`viewer` or `studylist`).
            @returns dict
        '''
        if field not in PREF_FIELDS:
            raise ValueError('Invalid preference field: %r' % field)
        value = getattr(self, field)
        return value if isinstance(value, dict) else {}

    def get_section(self, field, version, section=None):
        ''' Read a stored section without mutating the instance. When `section` is
            None the whole version document is returned (used by the studylist GET,
            whose version document is itself the interface map). A missing version or
            section resolves to an empty dict.

            @input field (str): `viewer` or `studylist`.
            @input version (str): Version key, e.g. `0.4`.
            @input section (str or None): Section key within the version document.
            @returns dict
        '''
        version_document = self._document(field).get(version) or {}
        if section is None:
            return version_document
        return version_document.get(section) or {}

    def set_section(self, field, version, section, values):
        ''' Replace `[version][section]` in `field` with `values`, creating the field
            and version document as needed. Other versions and sections are left
            untouched (FR-2). The instance is mutated in place but not saved.

            @returns the stored section values
        '''
        document = dict(self._document(field))
        version_document = dict(document.get(version) or {})
        version_document[section] = values
        document[version] = version_document
        setattr(self, field, document)
        return values

    def merge_interfaces(self, version, values):
        ''' FR-14 interface-level merge for the `studylist` field: every interface key
            present in `values` replaces that interface's stored subdocument entirely;
            interfaces absent from `values` are left unchanged. The instance is mutated
            in place but not saved.

            @input version (str): Version key, e.g. `0.4`.
            @input values (dict): Map of interface key -> subdocument.
            @returns the full stored version document after the merge
        '''
        document = dict(self._document('studylist'))
        version_document = dict(document.get(version) or {})
        for interface, subdocument in values.items():
            version_document[interface] = subdocument
        document[version] = version_document
        self.studylist = document
        return version_document

    # -- FR-12 legacy nesting transform (§5.3 item 5) ----------------------------------

    @staticmethod
    def nest_legacy_document(value, version=LEGACY_PREF_VERSION):
        ''' Return the FR-12 form of a preference document: a pre-existing,
            non-versioned (flat) document is nested under `version`; a document that is
            already versioned (every top-level key matches PREF_VERSION_RE) or is
            null/empty is returned unchanged. Pure and idempotent -- re-running against
            already-migrated data is a no-op.

            @input value (dict or None): The raw `viewer` or `studylist` field value.
            @returns the possibly-nested document
        '''
        if not value or not isinstance(value, dict):
            return value
        if all(PREF_VERSION_RE.match(key) for key in value.keys()):
            return value
        return {version: value}
