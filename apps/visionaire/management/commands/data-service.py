import six, os, logging, argparse, json
from collections import OrderedDict

from tabulate import tabulate

from django.core.management.base import CommandParser, CommandError
from django.core.paginator import Paginator

from guru.management.base import GuruBaseManagementCommand
from guru.management.validators import argparse_email_type

from guru import apisettings as gapicodes
from guru.helpers.utils import apisettings as gcapicodes
from guru.helpers import gsetting, datetime2str
from guru.helpers.utils.object import pick
from guru.helpers.utils.terminal import terminal_size
from guru.helpers.utils.format import formerrors2str

from ...auth.models.integrations import DataService

logger = logging.getLogger(__name__)


DATASERVICE_CMD_LIST = 'list'
DATASERVICE_CMD_CREATE = 'create'
DATASERVICE_CMD_UPDATE = 'update'
DATASERVICE_CMD_RM = 'rm'
DATASERVICE_CMD_DETAILS = 'details'
DATASERVICE_SUPPORTED_COMMANDS = (
	DATASERVICE_CMD_LIST, DATASERVICE_CMD_CREATE, DATASERVICE_CMD_DETAILS,
	DATASERVICE_CMD_UPDATE, DATASERVICE_CMD_RM)


DATASERVICE_LIST_PARAMS = OrderedDict((
		('token', 'Service ID'),
		('description', 'Description'),
		('active', 'Active'),
	))

DATASERVICE_DETAILS_PARAMS = OrderedDict((
		('description', 'Description'),
		('active', 'Data Service Active'),
	))


def add_dataservice_parser_arguments(parser, update=False):
	''' Add data service aguments to a parser/subparser instance: ID, description, active
	'''
	if update: dataservice_help = 'Unique ID of the dataservice.'
	else:
		dataservice_help = 'Service ID which should be used to identify the data service. The service ID must be alphanumeric, ' \
			+ 'cannot contain spaces, or user special/reserved characters. Once a service ID has been set ' \
			+ 'it cannot be changed. If no service ID is provided, one will be randomly generated.'

	parser.add_argument('--service', type=six.text_type, dest='service',
		default=os.environ.get('SONADOR_SERVICE_CLIENT_ID'), help=dataservice_help, required=update)
	parser.add_argument('--service-description', type=six.text_type, dest='service_description',
		default=os.environ.get('SONADOR_SERVICE_DESCRIPTION'), 
		help='Description for the data service. Can also be provided as the SONADOR_SERVICE_DESCRIPTION environment variable.')

	# Toggle whether the service allows staff 
	acl_allow_staff = parser.add_mutually_exclusive_group(required=False)
	acl_allow_staff.add_argument('--set-acl-allow-staff', dest='acl_allow_staff', default=None, action='store_true',
		help='Allow users in Sonador with the "staff" permission to access the data service.')
	acl_allow_staff.add_argument('--set-acl-disallow-staff', dest='acl_allow_staff', default=None, action='store_false',
		help='Prevents global access to the data service by "staff" users. Only users who are members of a specified group will '
			+ 'be able to authenticate.')
	
	# Toggle whether the service is active
	active_service = parser.add_mutually_exclusive_group(required=False)
	active_service.add_argument('--set-active', dest='active', default=None, action='store_true',
		help='Mark the data service as "active."')
	active_service.add_argument('--set-inactive', dest='active', default=None, action='store_false',
		help='Mark the data service as "inactive."')


def map_data_service_options(options, data, update=False, mappings={
		'service': 'token',
		'service_description': 'description',
	}):
	''' Map CLI options to the service data payload

		* service to token
		* service description to description

		@input options (dict): Dictionary of CLI arguments
		@input data (dict): Dictionary to which the parameters from options should be mapped

		@returns dict: returns the data structured passed in as data with parameters 
			from options included.
	'''
	for clik, cliv in six.iteritems(options):
		if clik in mappings:
			data[mappings.get(clik)] = cliv

	return data


class Command(GuruBaseManagementCommand):
	'''	Command line interface for Sonador data services. Provies subcommands to list
		services registered with Sonador, create new ones, retrieve details for a service instance,
		modify the configuration, or remove the service.
	'''
	def add_arguments(cmd, parser):
		'''	Add arguments/subcommands to the parser
		'''
		# Create a subparser class which can be used for adding subcommands like "list", "details", "rm", etc.
		class Subparser(CommandParser):
			def __init__(self, *args, **kwargs):
				super(Subparser, self).__init__(*args, **kwargs)

		# Create command subparser
		service_commands = parser.add_subparsers(dest='command', metavar='command', title='commands',
			parser_class=Subparser, help='Data Service Commands: %s' % ', '.join(DATASERVICE_SUPPORTED_COMMANDS))

		# List data services
		service_list = service_commands.add_parser(DATASERVICE_CMD_LIST,
			help='List data services registered with the Sonador instance')
		service_list.add_argument('--items', type=int, default=100, help='The number of items to include in the service list. '
			+ 'By default, the server will retrieve 100 items at a time.')
		service_list.add_argument('--page', type=int, default=1, help='The page of results to retrieve. Default: 1.')

		# Create new data service
		service_create = service_commands.add_parser(DATASERVICE_CMD_CREATE,
			help='Create a new data service in Sonador')
		add_dataservice_parser_arguments(service_create)

		# Update existing data service
		service_update = service_commands.add_parser(DATASERVICE_CMD_UPDATE,
			help='Update an existing data service in Sonador')
		add_dataservice_parser_arguments(service_update, update=True)

		# Show details for services
		service_details = service_commands.add_parser(DATASERVICE_CMD_DETAILS,
			help='Retrieve and display the details for the specified data services')
		service_details.add_argument('services', type=six.text_type, nargs='+', 
			help='Data services for which the details should be retrieved')

		# Remove data services
		service_remove = service_commands.add_parser(DATASERVICE_CMD_RM, 
			help='Remove data services from the Sonador instance')
		service_remove.add_argument('services', type=six.text_type, nargs='+', 
			help='Data services to be removed from Sonador')
	
	def list_data_services(self, *args, **options):
		paginator = Paginator(DataService.objects.all(), options.get('items'))
		page = paginator.get_page(options.get('page'))

		if len(page):
			
			# Prepare data for display
			stable = OrderedDict()
			for s in page:
				stable[s.pk] = tuple(
					getattr(s, attr) if hasattr(s, attr) else '' for attr in six.iterkeys(DATASERVICE_LIST_PARAMS))

			self.stdout.write('\n%s\n\nPage: %r, Results: %s'
				% (tabulate(six.itervalues(stable), headers=tuple(six.itervalues(DATASERVICE_LIST_PARAMS))), 
					options.get('page'), '%d - %d' % (((options.get('page')-1)*options.get('items')) or 1, options.get('page')*len(page))))
		
		else: self.stdout.write('\nNo data services have been registered with Sonador\n\n')
	
	def create_dataservice(self, *args, **options):
		'''	Create a new data service in Sonador
		'''
		if not options.get('service_description'):
			raise CommandError('Invalid data service configuration. A service description must be provided '
				+ 'via the CLI arguments or as an environment variable.')

		sdata = map_data_service_options(
			pick(options, ('service', 'service_description')), pick(options, ('active', 'acl_allow_staff')))
		logger.debug('Data service data: %s' % sdata)

		try:
			dservice = DataService.objects.create(**sdata)
			self.stdout.write('Data service %s (%s) created successfully\n' % (dservice.description, dservice.pk))

		except Exception as err:
			raise CommandError('Uanble to create data service %s (%s), an error occurred:\n%s'
				% (options.get('service_description'), options.get('service'), err))

	def update_dataservice(self, *args, **options):
		'''	Update an existing data service in Sonador
		'''
		update_service_params = map_data_service_options(
			pick(options, ('service_description', )), pick(options, ('active', 'acl_allow_staff')))

		# Update data service
		try:
			dservice = DataService.objects.get(pk=options.get('service'))
			for attr,val in six.iteritems(update_service_params):
				setattr(dservice, attr, val)
			dservice.save()
			self.stdout.write('Data service "%s" updated successfully\n' % options.get('service'))

		except DataService.DoesNotExist as err:
			raise CommandError('Unable to update data service "%s" invalid service ID.' % options.get('service'))

		except Exception as err:
			raise CommandError('Unable to update data service "%s", an error occurred:\n%s'
				% (options.get('service'), err))

	def remove_dataservices(self, *args, **options):
		'''	Remove data services from Sonador
		'''
		try: 
			services = DataService.objects.filter(pk__in=options.get('services', []))
			
			for s in services:

				# Cache reference to primay key, which will be set to None after removal.
				sid = s.pk

				# Remove service and log to stdout
				s.delete()
				self.stdout.write('Data service "%s" removed successfully' % sid)

		except Exception as err:
			raise CommandError('Unable to remove data services %s due to an error:\n%s'
				% (', '.join(options.get('services', [])), err))
	
	def handle(self, *args, **options):
		'''	Process the data service operation
		'''
		command = options.get('command')
		if not command in DATASERVICE_SUPPORTED_COMMANDS:
			raise CommandError('Unsupported command: "%s". Supported: %s.' 
				% ((options.get('command') or '(null)'), ', '.join(DATASERVICE_SUPPORTED_COMMANDS)))
		
		# List data services
		if command == DATASERVICE_CMD_LIST:
			self.list_data_services(*args, **options)

		# Create new data service
		elif command == DATASERVICE_CMD_CREATE:
			self.create_dataservice(*args, **options)
		
		# Update existing data service
		elif command == DATASERVICE_CMD_UPDATE:
			self.update_dataservice(*args, **options)

		# Remove data services servers
		elif command == DATASERVICE_CMD_RM:
			self.remove_dataservices(*args, **options)