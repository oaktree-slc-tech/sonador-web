'''	Post-initialization verification of the login round trip protections.

	Run by the container entrypoint after the schema is in place. Unlike the system check,
	which `migrate` runs before applying anything and which therefore tolerates the
	provider table being unreadable, this command treats a read failure as a failure: a
	deployment does not serve a login the protections could not be verified for.

	A relaxed protection is reported the way the system check reports it, so a deployment
	which silences `visionaire.E004` in SILENCED_SYSTEM_CHECKS passes here too; a read
	failure is not a check message and cannot be silenced.
'''
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from ...checks import login_protection_errors


class Command(BaseCommand):
	help = 'Verify that the identity provider behind the default authorization server keeps every login protection on'

	def handle(self, *args, **options):
		try: errors = login_protection_errors(strict=True)
		except DatabaseError as err:
			raise CommandError('Unable to read the default authorization server: %s' % err)

		errors = [error for error in errors if not error.is_silenced()]
		if errors:
			raise CommandError('\n'.join('%s (%s)\n\tHINT: %s' % (error.msg, error.id, error.hint)
				for error in errors))

		self.stdout.write('Login protections verified for the default authorization server.')
