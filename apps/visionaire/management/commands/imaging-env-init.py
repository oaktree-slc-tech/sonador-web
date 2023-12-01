import os, logging, time, six

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
SONADOR_IMAGING_SERVER_INTERNAL_SCHEME = os.environ.get('SONADOR_IMAGING_SERVER_INTERNAL_SCHEME')
SONADOR_IMAGING_SERVER_INTERNAL_HOSTNAME = os.environ.get('SONADOR_IMAGING_SERVER_INTERNAL_HOSTNAME')
SONADOR_IMAGING_SERVER_INTERNAL_PORT = os.environ.get('SONADOR_IMAGING_SERVER_INTERNAL_PORT')
SONADOR_IMAGING_SERVER_DEFAULT = os.environ.get('SONADOR_IMAGING_SERVER_DEFAULT')

OHIF_BUCKET_PATH = 'js/ohif/index.umd.js'


class Command(GuruBaseManagementCommand):
    """ Initializes the development environment for Sonador. Creates database migrations, create object storage
        bucket for site static assets, creates base user and initializes secure access credentials. Registers a
        default Orthanc imaging server.
    """
    parser_user_arguments = ('username', 'first_name', 'last_name', 'email', 'password')
    parser_sonador_arguments = ('sonador_hostname', 'sonador_description')

    def add_arguments(self, parser):
        ''' Provide argument overrides
        '''
        # Options for initializing and applying migrations and SCSS
        parser.add_argument('--nomigrations', dest='dbmigrations', default=True, action='store_false',
            help='Skip initialization of the database. No migrations are created or applied.')
        parser.add_argument('--skip-childmodel-migrations', dest='childmodel_migrations', default=True, action='store_false',
            help='Skip migration of inherited/child model instances.')
        parser.add_argument('--skip-collectstatic', dest='collectstatic', default=True, action='store_false',
            help='Skip deployment of static files as part of environment initialization.')
        parser.add_argument('--skip-compile-scss', dest='compilescss', default=True, action='store_false',
            help='Skip compiling SCSS as part of environment initialization.')

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

        # Sonador server parameters
        parser.add_argument('--sonador-hostname', dest='sonador_hostname', default=SONADOR_SERVER_HOSTNAME,
            help='Hostname for the Sonador server instance. Added to the site record for the instance.')
        parser.add_argument('--sonador-description', dest='sonador_description', default=SONADOR_SERVER_DESCRIPTION,
            help='Sonador server description. Added to the site record for the instance.')

    def compile_scss(self):
        '''Complile the scss
        '''
        try: call_command('compile-scss')
        except Exception as err:
            raise CommandError('Unable to compile css please ensure static files are configured and view logs for more details')

    def validate_options(self, options):
        ''' Ensure that the options provided to the command are complete
        '''
        if any(options.get(a) for a in self.parser_user_arguments) and any(options.get(a) is None for a in self.parser_user_arguments):
            raise CommandError('Invalid user arguments. Please ensure that all user arguments are set '
                + 'via the environment variables or CLI options, refer to --help for details.')
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
        try: call_command('migrate')
        except Exception as err:
            raise CommandError(f'Unable to initialize imaging server, an error occurred: {err}')

    def migrate_childmodels(self):
        ''' Migrate proxy model instances
        '''
        from secure.models import ApiAccess, ApiAccessToken
        from ...admin.auth import SonadorApiAccess, SonadorApiAccessToken

        # Iterate through child/parent models
        for smodel, model, pk_ptr_attr in (
                (SonadorApiAccess, ApiAccess, 'apiaccess_ptr_id'),
                (SonadorApiAccessToken, ApiAccessToken, 'apiaccesstoken_ptr_id')):

            # Locate model instances present in the parent not yet migrated to the child
            for m in model.objects.exclude(pk__in=smodel.objects.all().values_list('pk', flat=True)):

                # Create child model instance from parent attributes
                sm = smodel(**{ pk_ptr_attr: m.pk })
                sm.__dict__.update(m.__dict__)
                sm.save()

    def handle(self, *args, **options):
        ''' Initialize the imaging environment with the specified options
        '''
        self.validate_options(options)

        if options.get('compilescss'):
            self.compile_scss()
        else:
            self.stdout.write('--skip-compile-scss used, skip compiling SCSS')

        if options.get('dbmigrations'):

            # Call makemigrations recursively to account for delays in the initialization of the database.
            # When first launching the container environment, the database may not yet be available.
            count = 0
            self.makemigrations(count, 2)

            # Apply migrations
            self.migrate()

        else:
            self.stdout.write('--nomigrations used, skip initialization of database')

        # Migrate child models
        if options.get('childmodel_migrations'):
            print('Migrate child models')

            try: self.migrate_childmodels()
            except Exception as err:
                raise CommandError(f'Unable to initialize imaging environment, an error occurred while migrating child models: {err}')

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

        # Check on existing OHIF viewer on the directory and if doesn't collectstatic
        if options.get('collectstatic'):

            try: call_command('collectstatic', '--no-input')
            except Exception as err:
                raise CommandError(f'Unable to initialize imaging environment, an error occurred while uploading static files: {err}')

        else:
            self.stdout.write('--skip-collectstatic used, skip upload of static assets')
