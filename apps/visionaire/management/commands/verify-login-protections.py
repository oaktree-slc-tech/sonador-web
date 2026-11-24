'''	Post-initialization verification of the login round trip protections.

	Run by the container entrypoint after the schema is in place. Unlike the system check,
	which `migrate` runs before applying anything and which therefore tolerates the
	provider table being unreadable, this command treats a read failure as a failure whatever
	the enforcement setting: the provider configuration is then unknown, not relaxed.

	A provider record which relaxes a protection is reported the way the system check reports
	it: a warning (`visionaire.W004`) by default, and a failure (`visionaire.E004`) with
	`AUTH_ENFORCE_LOGIN_PROTECTIONS` on. Silencing the check in SILENCED_SYSTEM_CHECKS silences
	it here too; a read failure is not a check message and cannot be silenced.
'''
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from ...checks import enforce_login_protections, login_protection_messages


class Command(BaseCommand):
	help = 'Verify that the identity provider behind the default authorization server keeps every login protection on'

	def handle(self, *args, **options):
		try: messages = login_protection_messages(strict=True)
		except DatabaseError as err:
			raise CommandError('Unable to read the default authorization server: %s' % err)

		messages = [message for message in messages if not message.is_silenced()]
		report = '\n'.join('%s (%s)\n\tHINT: %s' % (message.msg, message.id, message.hint)
			for message in messages)

		if messages and enforce_login_protections():
			raise CommandError(report)

		if messages:
			self.stderr.write('WARNING: %s' % report)
			return

		self.stdout.write('Login protections verified for the default authorization server.')
