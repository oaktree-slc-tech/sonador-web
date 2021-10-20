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

from microservices.control import server_controlurl

from ...models import PacsImagingServer

logger = logging.getLogger(__name__)


ORTHANC_SERVER_CMD_LIST = 'list'
ORTHANC_SERVER_CMD_CREATE = 'create'
ORTHANC_SERVER_CMD_UPDATE = 'update'
ORTHANC_SERVER_CMD_RM = 'rm'
ORTHANC_SERVER_CMD_DETAILS = 'details'
ORTHANC_SUPPORTED_COMMANDS = (
	ORTHANC_SERVER_CMD_LIST, ORTHANC_SERVER_CMD_CREATE, ORTHANC_SERVER_CMD_DETAILS, 
	ORTHANC_SERVER_CMD_UPDATE, ORTHANC_SERVER_CMD_RM)


ORTHANC_SERVER_LIST_PARAMS = OrderedDict((
		('token', 'ID'),
		('name', 'Name'),
		('active', 'Active'),
		('description', 'Description'),
	))

ORTHANC_SERVER_DETAILS_PARAMS = OrderedDict((
		('name', 'Name'),
		('description', 'Description'),
		('active', 'Imaging Server Active'),
		('host', 'Hostname'),
		('port', 'Port'),
		('internal_hostname', 'Internal/Cluster Hostname'),
		('internal_port', 'Internal/Cluster Port'),
	))


def add_imaging_server_parser_arguments(parser, update=False):
	'''	Add imaging server data arguments to a parser/subparser instance: scheme, hostname, port, 
		internal_scheme, internal_hostname, internal_port.
	'''
	if update: server_help='Unique ID of the imaging server.'
	else:
		server_help = 'Server ID which should be used to identify the server. The server ID must be alphanumeric, ' \
			+ 'cannot contain spaces, or use special/reserved characters. Once a server ID has been set ' \
			+ 'it cannot be changed. If no server ID is provided, one will be randomly generated.'

	parser.add_argument('--server', type=six.text_type, dest='server', 
		default=os.environ.get('SONADOR_IMAGING_SERVER'), help=server_help, required=update)
	parser.add_argument('--server-name', type=six.text_type, dest='server_name',
		default=os.environ.get('SONADOR_IMAGING_SERVER_NAME'),  
		help='Name for the imaging server. Can also be provided as the SONADOR_IMAGING_SERVER_NAME '
			+ 'environment variable.')
	parser.add_argument('--server-description', type=six.text_type, dest='server_description',
		default=os.environ.get('SONADOR_IMAGING_SERVER_DESCRIPTION'),
		help='Imaging server description. Can also be provided as the SONADOR_IMAGING_SERVER_DESCRIPTION '
			+ 'environment variable.')

	parser.add_argument('--server-scheme', type=six.text_type, required=False, dest='server_scheme',
		default=os.environ.get('SONADOR_IMAGING_SERVER_SCHEME'),
		help='URL scheme to used when connecting to the server. Can also be provided as the '
			+ 'SONADOR_IMAGING_SERVER_SCHEME environment variable.')
	parser.add_argument('--server-hostname', type=six.text_type, required=False, dest='server_hostname',
		default=os.environ.get('SONADOR_IMAGING_SERVER_HOSTNAME'),
		help='Fully qualified domain for the imaging server. Can also be provided as the '
			+ 'SONADOR_IMAGING_SERVER_HOSTNAME environment variable.')
	parser.add_argument('--server-port', type=int, required=False, dest='server_port',
		default=os.environ.get('SONADOR_IMAGING_SERVER_PORT'),
		help='Server port of the imaging server.')

	parser.add_argument('--server-internal-scheme', type=six.text_type, required=False, dest='internal_scheme',
		default=os.environ.get('SONADOR_IMAGING_SERVER_INTERNAL_SCHEME'),
		help='URL scheme to be used when connecting to the server within the cluster/firewall. Can '
			+ 'also be provided as the SONADOR_IMAGING_SERVER_INTERNAL_SCHEME environment variable.')
	parser.add_argument('--server-internal-hostname', type=six.text_type, required=False, dest='internal_hostname',
		default=os.environ.get('SONADOR_IMAGING_SERVER_INTERNAL_HOSTNAME'),
		help='Fully qualified domain for the imaging server to be used within the cluster/firewall. '
			+ 'Can also be provided as the SONADOR_IMAGING_SERVER_INTERNAL_HOSTNAME environment variable.')
	parser.add_argument('--server-internal-port', type=int, required=False, dest='internal_port',
		default=os.environ.get('SONADOR_IMAGING_SERVER_INTERNAL_PORT'),
		help='Server port to use within the cluster/firewall. Can also be provided as the '
			+ 'SONADOR_IMAGING_SERVER_INTERNAL_PORT environment variable.')

	# Toggle whether the server should be specified as the "default" server
	default_server = parser.add_mutually_exclusive_group(required=False)
	default_server.add_argument('--set-default', dest='default', default=None, action='store_true',
		help='Sets the imaging server as the default for the Sonador instance.')
	default_server.add_argument('--unset-default', dest='default', default=None, action='store_false',
		help='Unsets the imaging server as the default for the Sonador instance.')

	# Toggle whether the server is active
	active_server = parser.add_mutually_exclusive_group(required=False)
	active_server.add_argument('--set-active', dest='active', default=None, action='store_true',
		help='Mark the imaging server as "active."')
	active_server.add_argument('--set-inactive', dest='active', default=None, action='store_false',
		help='Mark the imaging server as "inactive."')


def map_data_server_options(options, data, update=False, mappings={
		'server': 'token',
		'server_name': 'name',
		'server_description': 'description',
		'server_scheme': 'scheme',
		'server_hostname': 'hostname',
		'server_port': 'port',
	}):
	'''	Map CLI options to server data payload:

		* server to token
		* server_scheme, server_hostname, server_port to scheme, hostname, port

		@input options (dict): Dictionary of CLI arguments
		@input data (dict): Dictionary to which the parameers from options should be mapped

		@returns dict: returns thd data structured passed in as data with parameters
			from options included
	'''
	for clik, cliv in six.iteritems(options):
		if clik in mappings:
			data[mappings.get(clik)] = cliv

	return data


class Command(GuruBaseManagementCommand):
	'''	Command line interface for managing Orthanc imaging servers. Provies subcommands to list
		servers registered with Sonador, create new ones, retrieve details for a server instance,
		modify the configuration, or remove the server.
	'''
	def add_arguments(cmd, parser):
		'''	Add arguments/subcommands to the parser
		'''
		# Create a subparser class which can be used for adding subcommands like "list", "details", "rm", etc.
		class Subparser(CommandParser):
			def __init__(self, *args, **kwargs):
				super(Subparser, self).__init__(*args, **kwargs)

		# Create command subparser
		server_commands = parser.add_subparsers(dest='command', metavar='command', title='commands',
			parser_class=Subparser, help='Imaging Server Commands: %s' % ', '.join(ORTHANC_SUPPORTED_COMMANDS))

		# List imaging servers
		server_list = server_commands.add_parser(ORTHANC_SERVER_CMD_LIST,
			help='List imaging servers defined on the Sonador instance')
		server_list.add_argument('--items', type=int, default=100, help='The number of items to include in the server list. '
			+ 'By default, the server will retrieve 100 items at a time.')
		server_list.add_argument('--page', type=int, default=1, help='The page of results to retrieve. Default: 1.')

		# Create new imaging server
		server_create = server_commands.add_parser(ORTHANC_SERVER_CMD_CREATE,
			help='Create a new imaging server in Sonador')
		add_imaging_server_parser_arguments(server_create)

		# Update existing imaging server
		server_update = server_commands.add_parser(ORTHANC_SERVER_CMD_UPDATE,
			help='Update an existing imaging server in Sonador')
		add_imaging_server_parser_arguments(server_update, update=True)

		# Show details for servers
		server_details = server_commands.add_parser(ORTHANC_SERVER_CMD_DETAILS,
			help='Retrieve and display the details for the specified imaging servers')
		server_details.add_argument('servers', type=six.text_type, nargs='+', 
			help='Imaging servers for which the details should be retrieved')

		# Remove imaging servers
		server_remove = server_commands.add_parser(ORTHANC_SERVER_CMD_RM, 
			help='Remove imaging servers from the Sonador instance')
		server_remove.add_argument('servers', type=six.text_type, nargs='+', 
			help='Imaging servers to be removed from Sonador')

	def list_imaging_servers(self, *args, **options):
		paginator = Paginator(PacsImagingServer.objects.all(), options.get('items'))
		page = paginator.get_page(options.get('page'))

		if len(page):

			# Prepare data for display
			stable = OrderedDict()
			for s in page:
				stable[s.pk] = tuple(
					getattr(s, attr) if hasattr(s, attr) else '' for attr in six.iterkeys(ORTHANC_SERVER_LIST_PARAMS))

			self.stdout.write('\n%s\n\nPage: %r, Results: %s'
				% (tabulate(six.itervalues(stable), headers=tuple(six.itervalues(ORTHANC_SERVER_LIST_PARAMS))), 
					options.get('page'), '%d - %d' % (((options.get('page')-1)*options.get('items')) or 1, options.get('page')*len(page))))

		else: self.stdout.write('\nNo imaging servers have been registered with Sonador\n\n')

	def create_imaging_server(self, *args, **options):
		'''	Create a new imaging server in Sonador
		'''
		if not options.get('server_name') or not options.get('server_description'):
			raise CommandError('Invalid server configuration. A server name and description must be provided '
				+ 'via the CLI arguments or as an environment variable.')

		if not options.get('server_scheme') or not options.get('server_hostname') or not options.get('server_port'):
			raise CommandError('Invalid server configuration. Please specify a connection scheme, hostname, and port.')

		sdata = map_data_server_options(
			pick(options, ('server', 'server_name', 'server_description',
				'server_scheme', 'server_hostname', 'server_port')),
			pick(options, ('internal_scheme', 'internal_hostname', 'internal_port', 'active', 'default')))
		logger.debug('Imaging server data: %s' % sdata)

		try:
			iserver = PacsImagingServer.objects.create(**sdata)
			self.stdout.write('Imaging server %s (%s) created successfully\n' % (iserver.name, iserver.pk))

		except Exception as err:
			raise CommandError('Uanble to create imaging server %s (%s), an error occurred:\n%s'
				% (options.get('server_name'), options.get('server'), err))

	def update_imaging_server(self, *args, **options):
		'''	Update an existing imaging server in Sonador
		'''
		update_server_params = map_data_server_options(
			pick(options, ('server_name', 'server_description', 'server_scheme', 'server_hostname', 'server_port')),
			pick(options, ('internal_scheme', 'internal_hostname', 'internal_port', 'active', 'default')))

		# Update imaging server
		try:
			iserver = PacsImagingServer.objects.get(pk=options.get('server'))
			for attr,val in six.iteritems(update_server_params):
				setattr(iserver, attr, val)
			iserver.save()
			self.stdout.write('Imaging server "%s" updated successfully\n' % options.get('server'))

		except PacsImagingServer.DoesNotExist as err:
			raise CommandError('Unable to update imaging server "%s" invalid server ID.' % options.get('server'))

		except Exception as err:
			raise CommandError('Unable to update imaging server "%s", an error occurred:\n%s'
				% (options.get('server'), err))

	def remove_imaging_servers(self, *args, **options):
		'''	Remove imaging servers from Sonador
		'''
		try: 
			servers = PacsImagingServer.objects.filter(pk__in=options.get('servers', []))
			
			for s in servers:

				# Cache reference to primay key, which will be set to None after removal.
				sid = s.pk

				# Remove server and log to stdout
				s.delete()
				self.stdout.write('Imaging server "%s" removed successfully' % sid)

		except Exception as err:
			raise CommandError('Unable to remove servers %s due to an error:\n%s'
				% (', '.join(options.get('servers', [])), err))


	def handle(self, *args, **options):
		'''	Process the imaging server operation
		'''
		command = options.get('command')
		if not command in ORTHANC_SUPPORTED_COMMANDS:
			raise CommandError('Unsupported command: "%s". Supported: %s.' 
				% ((options.get('command') or '(null)'), ', '.join(ORTHANC_SUPPORTED_COMMANDS)))

		# List Imaging servers
		if command == ORTHANC_SERVER_CMD_LIST:
			self.list_imaging_servers(*args, **options)

		# Create new imaging server
		elif command == ORTHANC_SERVER_CMD_CREATE:
			self.create_imaging_server(*args, **options)

		# Update existing imaging server
		elif command == ORTHANC_SERVER_CMD_UPDATE:
			self.update_imaging_server(*args, **options)

		# Remove imaging servers
		elif command == ORTHANC_SERVER_CMD_RM:
			self.remove_imaging_servers(*args, **options)
