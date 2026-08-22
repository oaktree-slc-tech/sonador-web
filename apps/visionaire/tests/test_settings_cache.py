'''	Unit tests for the `CACHES` type coercion in `sonador.settings.base`.

	ConfigObj hands every scalar in `site.config` back as a string, and neither Django nor
	pymemcache repairs that before the option dict reaches `pymemcache.HashClient(...)`. The
	coercion under test is what stands between a site config and a memcached client that is
	either broken (`max_pool_size = '64'`) or silently misconfigured (`no_delay = 'False'`,
	which is a truthy string).

	The functions are pure -- a mapping in, a mapping out, no Django cache and no memcached
	node -- so the tests drive them directly. Where the input matters, it is parsed from real
	INI text through ConfigObj rather than hand-written as a dict, so that the test exercises
	the same string values a deployment would produce.
'''
from configobj import ConfigObj

from django.test import SimpleTestCase

from sonador.settings.base import (CACHE_PYMEMCACHE_OPTIONS, coerce_cache_config,
	coerce_cache_options, config_cache_scalar)


# The configuration from the 0.4.1 production incident, verbatim.
PRODUCTION_CACHE_CONFIG = '''
[Cache]
CACHE_ENABLED = True
[[CACHES]]
[[[default]]]
BACKEND = 'django.core.cache.backends.memcached.PyMemcacheCache'
LOCATION = 'sonador-memcached:11211',
TIMEOUT = 10
[[[[OPTIONS]]]]
use_pooling = True
max_pool_size = 64
pool_idle_timeout = 60
connect_timeout = 1.0
timeout = 1.0
no_delay = True
'''

MEMCACHED_BACKEND = 'django.core.cache.backends.memcached.PyMemcacheCache'


def parse_caches(config_text):
	'''	Parse INI text the way `settings.base` does and return its `[Cache][[CACHES]]` section.
	'''
	return ConfigObj(config_text.strip().splitlines())['Cache']['CACHES']


def memcached_cache(options=None, **overrides):
	'''	A minimal, valid memcached alias, as ConfigObj would hand it over (values as strings).
	'''
	cache = {'BACKEND': MEMCACHED_BACKEND, 'LOCATION': ['sonador-memcached:11211']}
	if options is not None:
		cache['OPTIONS'] = options
	cache.update(overrides)

	return {'default': cache}


class CacheConfigCoercionTests(SimpleTestCase):
	'''	End-to-end: a site config in, a mapping Django and pymemcache can consume out.
	'''

	def test_production_config_coerces_to_the_types_pymemcache_requires(self):
		coerced = coerce_cache_config(parse_caches(PRODUCTION_CACHE_CONFIG))['default']

		self.assertEqual(coerced['BACKEND'], MEMCACHED_BACKEND)
		self.assertEqual(coerced['LOCATION'], ['sonador-memcached:11211'])
		self.assertEqual(coerced['TIMEOUT'], 10)

		options = coerced['OPTIONS']
		self.assertIs(options['use_pooling'], True)
		self.assertIs(options['no_delay'], True)
		self.assertEqual(options['max_pool_size'], 64)
		self.assertEqual(options['connect_timeout'], 1.0)
		self.assertEqual(options['timeout'], 1.0)
		self.assertEqual(options['pool_idle_timeout'], 60)

		# The types are the point of the exercise, and `assertEqual` will not catch them:
		# 64 == 64.0 == True, and '64' is what production actually had.
		self.assertIsInstance(options['max_pool_size'], int)
		self.assertNotIsInstance(options['max_pool_size'], bool)
		self.assertIsInstance(options['connect_timeout'], float)
		self.assertIsInstance(coerced['TIMEOUT'], int)

	def test_the_input_mapping_is_not_mutated(self):
		caches = parse_caches(PRODUCTION_CACHE_CONFIG)
		coerce_cache_config(caches)

		self.assertEqual(caches['default']['OPTIONS']['max_pool_size'], '64')

	def test_absent_options_section_is_left_alone(self):
		coerced = coerce_cache_config(memcached_cache())

		self.assertNotIn('OPTIONS', coerced['default'])

	def test_empty_options_section_skips_coercion(self):
		coerced = coerce_cache_config(memcached_cache(options={}))

		self.assertEqual(coerced['default']['OPTIONS'], {})

	def test_options_of_a_non_memcached_backend_are_passed_through(self):
		# MAX_ENTRIES is a locmem option, not a pymemcache one, and must not be rejected by
		# the pymemcache table just because it shares the CACHES section with one.
		caches = {'sessions': {
			'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
			'LOCATION': 'sonador-sessions',
			'OPTIONS': {'MAX_ENTRIES': '5000'},
		}}
		coerced = coerce_cache_config(caches)

		self.assertEqual(coerced['sessions']['OPTIONS'], {'MAX_ENTRIES': '5000'})

	def test_every_alias_is_coerced(self):
		caches = memcached_cache(options={'max_pool_size': '64', 'use_pooling': 'True'})
		caches['fragments'] = dict(caches['default'], OPTIONS={'timeout': '2.5'})

		coerced = coerce_cache_config(caches)

		self.assertEqual(coerced['default']['OPTIONS']['max_pool_size'], 64)
		self.assertEqual(coerced['fragments']['OPTIONS']['timeout'], 2.5)


class CacheBooleanCoercionTests(SimpleTestCase):
	'''	Booleans are the silent half of the bug: a string never raises, it just reads truthy.
	'''

	def coerce(self, **options):
		return coerce_cache_options('default', options)

	def test_false_spelling_becomes_a_real_false(self):
		# The whole point: 'False' passed through untouched would enable the option.
		self.assertIs(self.coerce(no_delay='False')['no_delay'], False)
		self.assertIs(self.coerce(no_delay='no')['no_delay'], False)
		self.assertIs(self.coerce(no_delay='0')['no_delay'], False)

	def test_true_spelling_becomes_a_real_true(self):
		self.assertIs(self.coerce(use_pooling='True')['use_pooling'], True)
		self.assertIs(self.coerce(use_pooling='yes')['use_pooling'], True)
		self.assertIs(self.coerce(use_pooling='1')['use_pooling'], True)

	def test_an_already_typed_boolean_survives(self):
		self.assertIs(self.coerce(use_pooling=True)['use_pooling'], True)

	def test_a_misspelled_boolean_is_an_error_rather_than_false(self):
		with self.assertRaises(ValueError) as raised:
			self.coerce(no_delay='Flase')

		message = str(raised.exception)
		self.assertIn('no_delay', message)
		self.assertIn('true/false', message)
		self.assertIn("'Flase'", message)


class CacheNumericCoercionTests(SimpleTestCase):
	'''	Integers, floats, and the values that are parseable but not usable.
	'''

	def coerce(self, **options):
		return coerce_cache_options('default', options)

	def test_integers_and_floats_are_parsed(self):
		coerced = self.coerce(use_pooling='True', max_pool_size='64', retry_attempts='2',
			dead_timeout='60')

		self.assertEqual(coerced['max_pool_size'], 64)
		self.assertEqual(coerced['retry_attempts'], 2)
		self.assertEqual(coerced['dead_timeout'], 60.0)

	def test_a_fractional_pool_size_is_rejected(self):
		with self.assertRaises(ValueError) as raised:
			self.coerce(max_pool_size='64.5')

		self.assertIn('whole number', str(raised.exception))

	def test_a_boolean_is_not_accepted_as_a_pool_size(self):
		# int(True) is 1, so without this check "max_pool_size = True" is a pool of one.
		for spelling in ('True', 'yes', 'False', 'no'):
			with self.assertRaises(ValueError) as raised:
				self.coerce(max_pool_size=spelling)

			self.assertIn('boolean', str(raised.exception))

	def test_a_digit_is_still_a_number_not_a_boolean(self):
		# '1' and '0' are recognized boolean spellings as well; for a numeric option they are
		# quantities, and only the pool-size floor should reject them.
		self.assertEqual(self.coerce(retry_attempts='1')['retry_attempts'], 1)
		self.assertEqual(self.coerce(pool_idle_timeout='0')['pool_idle_timeout'], 0)

	def test_a_non_numeric_value_names_the_option_and_offers_guidance(self):
		with self.assertRaises(ValueError) as raised:
			self.coerce(max_pool_size='sixty-four')

		message = str(raised.exception)
		self.assertIn('max_pool_size', message)
		self.assertIn("'sixty-four'", message)
		self.assertIn('Uvicorn thread pool', message)

	def test_an_empty_pool_is_rejected(self):
		with self.assertRaises(ValueError) as raised:
			self.coerce(use_pooling='True', max_pool_size='0')

		self.assertIn('smallest', str(raised.exception))

	def test_a_zero_socket_timeout_is_rejected(self):
		with self.assertRaises(ValueError):
			self.coerce(connect_timeout='0')

	def test_a_negative_timeout_is_rejected(self):
		with self.assertRaises(ValueError):
			self.coerce(timeout='-1')

	def test_zero_is_allowed_where_pymemcache_gives_it_a_meaning(self):
		# 0 idle timeout keeps pooled connections forever; 0 retries is a valid failover policy.
		coerced = self.coerce(pool_idle_timeout='0', retry_attempts='0')

		self.assertEqual(coerced['pool_idle_timeout'], 0)
		self.assertEqual(coerced['retry_attempts'], 0)


class CacheOptionValidationTests(SimpleTestCase):
	'''	Names, shapes, and the combination that boots but does nothing.
	'''

	def test_an_unrecognized_option_is_rejected_at_boot(self):
		# pymemcache takes fixed keyword arguments, so a typo is a TypeError at the first
		# cache access -- inside a request, where it reads as an outage.
		with self.assertRaises(ValueError) as raised:
			coerce_cache_options('default', {'max_poolsize': '64'})

		message = str(raised.exception)
		self.assertIn('max_poolsize', message)
		self.assertIn('max_pool_size', message)

	def test_the_rejection_lists_every_supported_option(self):
		with self.assertRaises(ValueError) as raised:
			coerce_cache_options('default', {'serde': 'pickle'})

		message = str(raised.exception)
		for name in CACHE_PYMEMCACHE_OPTIONS:
			self.assertIn(name, message)

	def test_errors_point_at_the_site_config_location(self):
		# An operator has to be able to find the line; the message is the only guide they get.
		with self.assertRaises(ValueError) as raised:
			coerce_cache_options('sessions', {'timeout': 'fast'})

		self.assertIn('[Cache][[CACHES]][[[sessions]]][[[[OPTIONS]]]]', str(raised.exception))

	def test_a_nested_section_where_a_value_belongs_is_rejected(self):
		with self.assertRaises(ValueError) as raised:
			coerce_cache_options('default', {'timeout': {'seconds': '1'}})

		self.assertIn('single value', str(raised.exception))

	def test_a_key_prefix_is_encoded_for_pymemcache(self):
		# pymemcache concatenates key_prefix with already-encoded keys.
		self.assertEqual(coerce_cache_options('default', {'key_prefix': 'sonador'})['key_prefix'],
			b'sonador')

	def test_a_pool_size_without_pooling_warns(self):
		# Parses, boots, and every worker thread still shares one connection: exactly the
		# production failure, so it must not pass silently.
		with self.assertWarns(UserWarning) as warned:
			coerce_cache_options('default', {'max_pool_size': '64', 'use_pooling': 'False'})

		self.assertIn('use_pooling', str(warned.warning))

	def test_a_sized_pool_with_pooling_on_does_not_warn(self):
		import warnings

		with warnings.catch_warnings(record=True) as caught:
			warnings.simplefilter('always')
			coerce_cache_options('default', {'max_pool_size': '64', 'use_pooling': 'True'})

		self.assertEqual(caught, [])


class CacheAliasValidationTests(SimpleTestCase):
	'''	Cache-level keys: the ones Django reads directly rather than forwarding to the client.
	'''

	def test_timeout_is_coerced_to_an_integer(self):
		coerced = coerce_cache_config(memcached_cache(TIMEOUT='300'))

		self.assertEqual(coerced['default']['TIMEOUT'], 300)

	def test_timeout_none_means_entries_never_expire(self):
		self.assertIsNone(coerce_cache_config(memcached_cache(TIMEOUT='None'))['default']['TIMEOUT'])
		self.assertIsNone(coerce_cache_config(memcached_cache(TIMEOUT='none'))['default']['TIMEOUT'])

	def test_a_bad_timeout_is_an_error_rather_than_django_s_silent_default(self):
		# Django's BaseCache does int(TIMEOUT) and substitutes 300 on failure, so without this
		# the cache runs with a lifetime nobody configured.
		with self.assertRaises(ValueError) as raised:
			coerce_cache_config(memcached_cache(TIMEOUT='five minutes'))

		message = str(raised.exception)
		self.assertIn('TIMEOUT', message)
		self.assertIn('seconds', message)

	def test_a_negative_timeout_is_rejected(self):
		with self.assertRaises(ValueError):
			coerce_cache_config(memcached_cache(TIMEOUT='-1'))

	def test_version_is_coerced_to_an_integer(self):
		coerced = coerce_cache_config(memcached_cache(VERSION='2'))

		self.assertEqual(coerced['default']['VERSION'], 2)

	def test_a_bad_version_is_rejected(self):
		with self.assertRaises(ValueError) as raised:
			coerce_cache_config(memcached_cache(VERSION='latest'))

		self.assertIn('VERSION', str(raised.exception))

	def test_a_missing_backend_is_rejected(self):
		with self.assertRaises(ValueError) as raised:
			coerce_cache_config({'default': {'LOCATION': 'sonador-memcached:11211'}})

		self.assertIn('BACKEND', str(raised.exception))

	def test_a_memcached_cache_without_a_location_is_rejected(self):
		with self.assertRaises(ValueError) as raised:
			coerce_cache_config({'default': {'BACKEND': MEMCACHED_BACKEND}})

		self.assertIn('LOCATION', str(raised.exception))

	def test_an_alias_that_is_not_a_section_is_rejected(self):
		with self.assertRaises(TypeError) as raised:
			coerce_cache_config({'default': MEMCACHED_BACKEND})

		self.assertIn('section', str(raised.exception))

	def test_options_that_are_not_a_section_are_rejected(self):
		with self.assertRaises(TypeError) as raised:
			coerce_cache_config(memcached_cache(options=['use_pooling']))

		self.assertIn('OPTIONS', str(raised.exception))


class ConfigCacheScalarTests(SimpleTestCase):
	'''	The scalar parser on its own, including the cases the option table never reaches.
	'''

	def test_text_is_returned_unchanged(self):
		self.assertEqual(config_cache_scalar('ascii', str), 'ascii')

	def test_bytes_are_returned_unchanged(self):
		self.assertEqual(config_cache_scalar(b'sonador', bytes), b'sonador')

	def test_a_non_ascii_key_prefix_is_rejected(self):
		with self.assertRaises(ValueError) as raised:
			config_cache_scalar('sonadør', bytes)

		self.assertIn('ASCII', str(raised.exception))

	def test_a_missing_value_is_rejected_rather_than_coerced(self):
		with self.assertRaises(ValueError):
			config_cache_scalar(None, int)
