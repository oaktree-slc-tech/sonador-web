import os, logging

from django.core.management.base import CommandError
from django.core.management import call_command
from guru.management.base import GuruBaseManagementCommand

from django.contrib.staticfiles.storage import staticfiles_storage

logger = logging.getLogger(__name__)

# Sonador imaging environment user credentials
SONADOR_USER_USERNAME = os.environ.get("SONADOR_USERNAME", "sonador_development")
SONADOR_USER_FIRST_NAME = os.environ.get("SONADOR_USER_FIRST_NAME", "sonador")
SONADOR_USER_LAST_NAME = os.environ.get("SONADOR_USER_LAST_NAME", "development")
SONADOR_USER_EMAIL = os.environ.get("SONADOR_USER_EMAIL", "sonador@gmail.com")
SONADOR_USER_PASSWORD = os.environ.get("SONADOR_USER_PASSWORD", "sonador_development_password")

# Orthanc server parameters
SONADOR_IMAGING_SERVER_NAME = os.environ.get("SONADOR_IMAGING_SERVER_NAME", "orthanc_development")
SONADOR_IMAGING_SERVER_DESCRIPTION = os.environ.get(
    "SONADOR_IMAGING_SERVER_DESCRIPTION", "orthanc development description"
)
SONADOR_IMAGING_SERVER_SCHEME = os.environ.get("SONADOR_IMAGING_SERVER_SCHEME", "http")
SONADOR_IMAGING_SERVER_HOSTNAME = os.environ.get("SONADOR_IMAGING_SERVER_HOSTNAME", "127.0.0.1")
SONADOR_IMAGING_SERVER_PORT = os.environ.get("SONADOR_IMAGING_SERVER_PORT", 8042)

OHIF_BUCKET_PATH = 'js/OHIF'


class Command(GuruBaseManagementCommand):
    """ Initializing development environment for Sonador
        Makes migrations commands, checks object storage bucket on existing and if doesn't
        initialize it making collectstatic command.
        Creates base user and intializes api access token for him. Creates default Orthanc imaging server.
    """

    def handle(self, *args, **options):
        # call makemigrations command
        try:
            call_command('makemigrations')
        except Exception as err:
            raise CommandError(f'Unable to initialize imaging environment, an error occurred: {err}')
        # call migrate command
        try:
            call_command('migrate')
        except Exception as err:
            raise CommandError(f'Unable to initialize imaging environment, an error occurred: {err}')

        # Intialize user api credentials for the Sondor Imaging environmnet
        try:
            call_command(f'api-user-credentials', f'{SONADOR_USER_USERNAME}',
                '--first-name', f'{SONADOR_USER_FIRST_NAME}',
                '--last-name', f'{SONADOR_USER_LAST_NAME}',
                '--email', f'{SONADOR_USER_EMAIL}',
                '--password', f'{SONADOR_USER_PASSWORD}'
            )
        except Exception as err:
            raise CommandError(f'Unable to initialize imaging environment, an error occurred: {err}')


        try:
            call_command(f'imaging-server', 'create',
                '--server-name', f'{SONADOR_IMAGING_SERVER_NAME}',
                '--server-description', f'{SONADOR_IMAGING_SERVER_DESCRIPTION}',
                '--server-scheme', f'{SONADOR_IMAGING_SERVER_SCHEME}',
                '--server-hostname', f'{SONADOR_IMAGING_SERVER_HOSTNAME}',
                '--server-port', f'{SONADOR_IMAGING_SERVER_PORT}'
            )
        except Exception as err:
            raise CommandError(f'Unable to initialize imaging environment, an error occurred: {err}')

        # Check on existing OHIF viewer on the directory and if doesn't collectstatic
        if not staticfiles_storage.exists(OHIF_BUCKET_PATH):
            try:
                call_command('collectstatic', '--no-input')
            except Exception as err:
                raise CommandError(f'Unable to initialize imaging environment, an error occurred: {err}')
