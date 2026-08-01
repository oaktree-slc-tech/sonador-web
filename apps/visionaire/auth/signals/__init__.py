'''	Authentication signal receivers.

	Importing this package is what connects them, so it has to be imported from the app's
	`ready()`. It was previously empty, which left `events.revoke_openid_access_token` written but
	never registered.
'''
from . import events
