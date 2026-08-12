'''	Audit signal declaration.

	One signal carries every audit event; the kind of event is a keyword argument
	(`event_type`) rather than a separate signal. Adding an event means adding a constant
	and a code mapping in `apisettings`, not wiring a new signal and receiver. This is the
	same shape the Orthanc plugin's producer already uses, where every message kind goes
	to one topic and is discriminated by an opcode.

	IMPORTANT: the signal takes no constructor arguments. `Signal(['a', 'b'])` -- the
	`providing_args` form -- was deprecated in Django 3.0 and removed in 4.0, so under
	Django 5.2 that list binds to `use_caching` and silently turns on receiver caching.
	The in-repo `visionaire.auth.signals.signals.socialuser_first_login` declaration still
	uses the removed form and is not a model to copy.
'''
import django.dispatch


sonador_audit_event = django.dispatch.Signal()
