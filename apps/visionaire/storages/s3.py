from guru import apisettings as gapicodes
from guru.helpers import gsetting

from largefiles import apisettings as ofapicodes
from largefiles.helpers import cors_domainlist
from largefiles.storages.s3 import S3Boto3Storage, AWS_S3_ACL_PUBLIC_READ

HOSTS_HTTP = cors_domainlist(gsetting('ALLOWED_HOSTS', []), scheme=gapicodes.HTTP)
HOSTS_HTTPS = cors_domainlist(gsetting('ALLOWED_HOSTS', []), scheme=gapicodes.HTTPS)

SONADOR_CORS_CONFIG = {
    'CORSRules': [{
        'AllowedHeaders': ['Authorization'],
        'AllowedMethods': ['GET'],
        'AllowedOrigins': sorted(list(set(
            tuple(gsetting('ALLOWED_HOSTS', [])) + tuple(HOSTS_HTTP) + tuple(HOSTS_HTTPS)))),
        'ExposeHeaders': ['GET'],
        'MaxAgeSeconds': 3000,
    }]
}


class SonadorS3StaticFilesStorage(S3Boto3Storage):
    '''	Storage provider which can be used for Mail Gorilla static files
    '''
    container = gsetting('AWS_S3_STATIC_CONTAINER')
    container_acl = AWS_S3_ACL_PUBLIC_READ
    container_cors = SONADOR_CORS_CONFIG if gsetting('OBJECT_STORAGE_TYPE') == ofapicodes.API_OBJECT_STORAGE_S3 \
        else None

    default_acl = AWS_S3_ACL_PUBLIC_READ
    verify_file_urls = False


class SonadorS3MediaFilesStorage(S3Boto3Storage):
    '''	Storage provider which can be used for for Mail Gorilla public media files
    '''
    container = gsetting('AWS_S3_MEDIA_CONTAINER')
    container_acl = AWS_S3_ACL_PUBLIC_READ
    container_cors = SONADOR_CORS_CONFIG if gsetting('OBJECT_STORAGE_TYPE') == ofapicodes.API_OBJECT_STORAGE_S3 \
        else None

    default_acl = AWS_S3_ACL_PUBLIC_READ
    verify_file_urls = False

    def _get_or_create_bucket(self, name):
        bucket = super(SonadorS3MediaFilesStorage, self)._get_or_create_bucket(name)
        return bucket
        