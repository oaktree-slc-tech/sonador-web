import os, logging, time

from django.core.management.base import CommandError
from django.core.management import call_command

from django.contrib.sites.models import Site

from guru.management.base import GuruBaseManagementCommand
from guru.helpers import gsetting, str2bool
from guru.helpers.utils.object import pick

from django.contrib.staticfiles.storage import staticfiles_storage

logger = logging.getLogger(__name__)


# Sonador imaging environment user credentials
SONADOR_USER_USERNAME = os.environ.get("SONADOR_USERNAME")
SONADOR_USER_FIRST_NAME = os.environ.get("SONADOR_USER_FIRST_NAME")
SONADOR_USER_LAST_NAME = os.environ.get("SONADOR_USER_LAST_NAME")
SONADOR_USER_EMAIL = os.environ.get("SONADOR_USER_EMAIL")
SONADOR_USER_PASSWORD = os.environ.get("SONADOR_USER_PASSWORD")
SECURE_API_APITOKEN = os.environ.get("SECURE_API_APITOKEN")

# Sonador server parameters
SONADOR_SERVER_HOSTNAME = os.environ.get('SONADOR_SERVER_HOSTNAME')
SONADOR_SERVER_DESCRIPTION = os.environ.get('SONADOR_SERVER_DESCRIPTION')

# Orthanc server parameters
SONADOR_IMAGING_SERVER = os.environ.get('SONADOR_IMAGING_SERVER')
SONADOR_IMAGING_SERVER_NAME = os.environ.get("SONADOR_IMAGING_SERVER_NAME")
SONADOR_IMAGING_SERVER_DESCRIPTION = os.environ.get(
    "SONADOR_IMAGING_SERVER_DESCRIPTION"
)
SONADOR_IMAGING_SERVER_SCHEME = os.environ.get("SONADOR_IMAGING_SERVER_SCHEME")
SONADOR_IMAGING_SERVER_HOSTNAME = os.environ.get("SONADOR_IMAGING_SERVER_HOSTNAME")
SONADOR_IMAGING_SERVER_PORT = os.environ.get("SONADOR_IMAGING_SERVER_PORT")
SONADOR_IMAGING_SERVER_DEFAULT = os.environ.get('SONADOR_IMAGING_SERVER_DEFAULT')

OHIF_BUCKET_PATH = 'js/ohif/index.umd.js'


class Command(GuruBaseManagementCommand):
    """ Initializes the development environment for Sonador. Creates database migrations, create object storage
        bucket for site static assets, creates base user and initializes secure access credentials. Registers a
        default Orthanc imaging server.
    """
    parser_user_arguments = ('username', 'first_name', 'last_name', 'email', 'password')
    parser_server_arguments = ('server', 'server_name', 'server_description', 'server_scheme', 'server_hostname', 'server_port')
    parser_sonador_arguments = ('sonador_hostname', 'sonador_description')

    def add_arguments(self, parser):
        ''' Provide argument overrides
        '''
        # Sonador imaging environment user credentials (defaults are taken from the environment variables)
        parser.add_argument('--username', dest='username', default=SONADOR_USER_USERNAME,
            help='Account username. May also be provided via the SONADOR_USER_USERNAME environment variable.')
        parser.add_argument('--first-name', dest='first_name', default=SONADOR_USER_FIRST_NAME,
            help='First name of user. May also be provided via the SONADOR_USER_FIRST_NAME environment variable.')
        parser.add_argument('--last-name', dest='last_name', default=SONADOR_USER_LAST_NAME, 
            help='Last name of user. May also be provided via the SONADOR_USER_LAST_NAME environment variable.')
        parser.add_argument('--email', dest='email', default=SONADOR_USER_EMAIL, 
            help='Email of user. May also be provided via the SONADOR_USER_EMAIL environment variable.')
        parser.add_argument('--password', dest='password', default=SONADOR_USER_PASSWORD,
            help='Account password. May also be provided via the SONADOR_USER_PASSWORD environment variable.')
        parser.add_argument('--apitoken-value', dest='apitoken_value', default=SECURE_API_APITOKEN, 
            help='Secure access token for the account. May also be provided via the SECURE_API_APITOKEN environment variable.')

        # Orthanc server parameters
        parser.add_argument('--server', dest='server', default=SONADOR_IMAGING_SERVER,
            help='Imaging server unique identifier. May also be provided via the SONADOR_IMAGING_SERVER environment variable.')
        parser.add_argument('--server-name', dest='server_name', default=SONADOR_IMAGING_SERVER_NAME,
            help='Imaging server name. May also be provided via the SONADOR_IMAGING_SERVER_NAME environment variable.')
        parser.add_argument('--server-description', dest='server_description', default=SONADOR_IMAGING_SERVER_DESCRIPTION,
            help='Imaging server description. May also be provided via the SONADOR_IMAGING_SERVER_DESCRIPTION environment variable.')
        parser.add_argument('--server-scheme', dest='server_scheme', default=SONADOR_IMAGING_SERVER_SCHEME,
            help='Imaging server connection scheme. May also be provided via the SONADOR_IMAGING_SERVER_SCHEME environment variable.')
        parser.add_argument('--server-hostname', dest='server_hostname', default=SONADOR_IMAGING_SERVER_HOSTNAME,
            help='Imaging server hostname. May also be provided via the SONADOR_IMAGING_SERVER_HOSTNAME environment variable.')
        parser.add_argument('--server-port', dest='server_port', default=SONADOR_IMAGING_SERVER_PORT,
            help='Imaging server port. May also be provided via the SONADOR_IMAGING_SERVER_PORT environment variable.')
        parser.add_argument('--server-default', dest='server_default', default=str2bool(SONADOR_IMAGING_SERVER_DEFAULT),
            help='Should the server be specified as the default for the Sonador instance. May also be provided via the SONADOR_IMAGING_SERVER_DEFAULT '
                + 'environment variable.')

        # Sonador server parameters
        parser.add_argument('--sonador-hostname', dest='sonador_hostname', default=SONADOR_SERVER_HOSTNAME,
            help='Hostname for the Sonador server instance. Added to the site record for the instance.')
        parser.add_argument('--sonador-description', dest='sonador_description', default=SONADOR_SERVER_DESCRIPTION,
            help='Sonador server description. Added to the site record for the instance.')

    def validate_options(self, options):
        ''' Ensure that the options provided to the command are complete
        '''
        if any(options.get(a) for a in self.parser_user_arguments) and any(options.get(a) is None for a in self.parser_user_arguments):
            raise CommandError('Invalid user arguments. Please ensure that all user arguments are set '
                + 'via the environment variables or CLI options, refer to --help for details.')
        if any(options.get(a) for a in self.parser_server_arguments) and any(options.get(a) is None for a in self.parser_server_arguments):
            raise CommandError('Invalid server arguments. Please ensure that all server arguments are '
                + 'set via the environment variables or CLI options, refer to --help for details.')
        if any(options.get(a) for a in self.parser_sonador_arguments) and any(options.get(a) is None for a in self.parser_sonador_arguments):
            raise CommandError('Invalid Sonador hostname or description. Please ensure that all Sonador arguments are '
                + 'set via the environment variables or CLI options, refer to --help for details.')

    def makemigrations(self, count, sleep_time, count_limit=3):
        ''' Create migrations for project applications.
        '''
        time.sleep(sleep_time)
        if count >= count_limit:
            raise CommandError('Unable to create database migrations. Please ensure that the database is online and available.')

        try: call_command('makemigrations')
        except Exception as err:
            self.makemigrations(count+1, sleep_time, count_limit=count_limit)

    def migrate(self):
        ''' Apply application database migrations
        '''
        try:
            call_command('migrate')
        except Exception as err:
            raise CommandError(f'Unable to initialize imaging server, an error occurred: {err}')


    def imagingServerArgs(self, server, server_name, server_description, server_scheme, server_hostname, server_port, server_default):
        ''' Determine arguments for imaging server operation (create/update)
        '''
        # Server ID, name, description, and connection params
        args = (
            '--server', f'{server}',
            '--server-name', f'{server_name}',
            '--server-description', f'{server_description}',
            '--server-scheme', f'{server_scheme}',
            '--server-hostname', f'{server_hostname}',
            '--server-port', f'{server_port}'
        )

        # Toggle whether the server should be Sonador default
        if server_default:
            args += ('--set-default',)
        elif server_default == False:
            args += ('--unset-default',)

        return args

    def createImagingServer(self, server, server_name, server_description, server_scheme, server_hostname, server_port, server_default):
        ''' Create a Sonador Imaging server with the provided arguments
        '''
        try:
            args = self.imagingServerArgs(server, server_name, server_description, server_scheme, server_hostname, server_port, server_default)
            call_command(f'imaging-server', 'create', *args)
        except Exception as err:
            raise CommandError(f'Unable to initialize imaging server, an error occurred: {err}')

    def updateImagingServer(self, server, server_name, server_description, server_scheme, server_hostname, server_port, server_default):
        ''' Update an existing server definition
        '''
        try:
            args = self.imagingServerArgs(server, server_name, server_description, server_scheme, server_hostname, server_port, server_default)
            call_command(f'imaging-server', 'update', *args)
        except Exception as err:
            raise CommandError(f'Unable to update imaging server, an error occurred: {err}')

    def init_imaging_server(self, *args, **kwargs):
        ''' Initialize (or update) the development server
        '''
        try: self.createImagingServer(*args, **kwargs)
        except Exception as err:
            try:
                self.updateImagingServer(*args, **kwargs)
            except Exception as err:
                raise CommandError(f'Unable to initialize imaging server, an error occurred: {err}')


    def handle(self, *args, **options):
        ''' Initialize the imaging environment with the specified options
        '''
        self.validate_options(options)
        
        # Call makemigrations recursively to account for delays in the initialization of the database.
        # When first launching the container environment, the database may not yet be available.
        count = 0
        self.makemigrations(count, 2)

        # Apply migrations
        self.migrate()

        # Create API user
        if options.get('username'):

            username = options['username']
            first_name = options['first_name']
            last_name = options['last_name']
            user_email = options['email']
            user_password = options['password']
            user_apitoken_value = options.get('apitoken_value')

            command_args = (
                f'api-user-credentials', 
                '--first-name', f'{first_name}',
                '--last-name', f'{last_name}',
                '--email', f'{user_email}',
                '--password', f'{user_password}'
            )

            if user_apitoken_value:
                command_args = command_args + ('--create-apitoken', '--apitoken-value', f'{user_apitoken_value}',)

            command_args = command_args + ('--skip-api-credentials', '--staff', '--super-user', f'{username}',)

            try: call_command(*command_args)
            except Exception as err:
                raise CommandError(f'Unable to initialize imaging environment, an error occurred: {err}')

        # Update Sonador site hostname and description from CLI arguments
        if gsetting('SITE_ID') and options.get('sonador_hostname'):
            try:
                csite = Site.objects.get(pk=int(gsetting('SITE_ID')))
                csite.domain = options.get('sonador_hostname')
                csite.name = options.get('sonador_description')
                csite.save()

                self.stdout.write('Sonador server name (%s) and domain (%s) configured successfully'
                    % (options.get('sonador_hostname'), options.get('sonador_description')))

            except Exception as err:
                raise CommandError('Unable to configure Sonador site hostname and description.\nID=%s hostname=%s description="%s"'
                    % (gsetting('SITE_ID'), options.get('sonador_hostname'), options.get('sonador_description')))

        # Initialize/update development server instance
        self.init_imaging_server(*args, **pick(options, 
            ('server', 'server_name', 'server_description', 'server_scheme', 'server_hostname', 'server_port', 'server_default')))

        # Check on existing OHIF viewer on the directory and if doesn't collectstatic
        if not staticfiles_storage.exists(OHIF_BUCKET_PATH):
            try:
                call_command('collectstatic', '--no-input')
            except Exception as err:
                raise CommandError(f'Unable to initialize imaging environment, an error occurred: {err}')