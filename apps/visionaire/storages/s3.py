import logging, json
from botocore.exceptions import ClientError as S3ClientError

from guru import apisettings as gapicodes
from guru.helpers import gsetting

from largefiles import apisettings as ofapicodes
from largefiles.helpers import cors_domainlist
from largefiles.storages.s3 import S3Boto3Storage, AWS_S3_ACL_PUBLIC_READ

logger = logging.getLogger(__name__)


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


SONAODR_MINIO_READONLY_POLICY_RESOURCE_TEMPLATE = 'arn:aws:s3:::%s/*'


class SonadorS3StaticFilesStorage(S3Boto3Storage):
    '''	Storage provider which can be used for Mail Gorilla static files
    '''
    container = gsetting('AWS_S3_STATIC_CONTAINER')
    container_acl = AWS_S3_ACL_PUBLIC_READ
    container_cors = SONADOR_CORS_CONFIG if gsetting('OBJECT_STORAGE_TYPE') == ofapicodes.API_OBJECT_STORAGE_S3 \
        else None

    default_acl = AWS_S3_ACL_PUBLIC_READ
    verify_file_urls = False

    def _create_bucket(self, name, bucket):        
        super(SonadorS3StaticFilesStorage, self)._create_bucket(name, bucket)
        
        if gsetting('OBJECT_STORAGE_TYPE') == ofapicodes.API_OBJECT_STORAGE_S3_MINIO \
            and getattr(self, 'default_acl', None) == AWS_S3_ACL_PUBLIC_READ:

            try: s3r = bucket.meta.client.get_bucket_policy(Bucket=name)
            except S3ClientError as err:
                logger.warning('Unable to retrieve bucket policy data. Error: %s. Initialize bucket settings with %s as a default storage policy.' 
                    % (err, self.default_acl))
                s3r = {}

            if not s3r.get('Policy'):
                s3policy = json.dumps({
                    'Version': '2012-10-17',
                    'Statement': [{
                        'Sid': 'AddPerm',
                        'Effect': 'Allow',
                        'Principal': '*',
                        'Action': ['s3:GetObject'],
                        'Resource': SONAODR_MINIO_READONLY_POLICY_RESOURCE_TEMPLATE % name,
                    }]
                })
                bucket.meta.client.put_bucket_policy(Bucket=name, Policy=s3policy)
                logger.debug('Initialize bucket with a default ACL for MinIO. Storage type: %s. Default ACL: %s. Policy to apply:\n%r'
                    % (gsetting('OBJECT_STORAGE_TYPE'), getattr(self, 'default_acl', None),  s3policy))

            logger.info('Bucket %s ACL configuration. Storage type: %s. Default ACL: %s. Policies:\n%r'
                % (name, gsetting('OBJECT_STORAGE_TYPE'), getattr(self, 'default_acl', None), bucket.meta.client.get_bucket_policy(Bucket=name)))


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
        
    def _create_bucket(self, name, bucket, *args, **kwargs):
        super(SonadorS3MediaFilesStorage, self)._create_bucket(name, bucket, *args, **kwargs)
