from django.conf import settings
from storages.backends.gcloud import GoogleCloudStorage
from storages.utils import setting
from urllib.parse import urljoin

from guru.helpers import gsetting


class GoogleCloudMediaStorage(GoogleCloudStorage):
    """GoogleCloudStorage suitable for Django's Media files."""

    def get_default_settings(self):
        settings = super().get_default_settings()
        settings['bucket_name'] = gsetting("GS_MEDIA_BUCKET")
        return settings

    def url(self, name):
        """.url that doesn't call Google."""
        return urljoin(gsetting('MEDIA_URL'), name)


class GoogleCloudStaticStorage(GoogleCloudStorage):
    """GoogleCloudStorage suitable for Django's Static files"""

    def get_default_settings(self):
        settings = super().get_default_settings()
        settings['bucket_name'] = gsetting("GS_STATIC_BUCKET")
        return settings

    def url(self, name):
        """.url that doesn't call Google."""
        return urljoin(gsetting('STATIC_URL'), name)