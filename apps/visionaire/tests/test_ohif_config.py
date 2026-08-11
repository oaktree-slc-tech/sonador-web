'''	Unit tests for the version reported by the OHIF application configuration document.

	A Sonador installation is three separately released pieces of software -- the web application,
	the imaging server (Orthanc plus the Sonador cloud plugin), and the viewer -- and in the field
	they are routinely not in step. The viewer therefore reports all three in its About panel, and
	the web application's own version reaches it through this document, which is the only channel
	the frontend already fetches on every boot.

	Exercised through the URL stack with the test client rather than by calling the view directly:
	the value has to survive both the view's context and the JSON template, and it is the rendered
	document -- which must stay parseable -- that the viewer actually consumes.
'''
import json

from django.test import TestCase, override_settings
from django.urls import reverse


class OhifConfigVersionTests(TestCase):
	'''	`settings.SONADOR_VERSION` is surfaced to the viewer as `sonadorVersion`.
	'''

	def get_config(self):
		response = self.client.get(reverse('ohif-config'))
		self.assertEqual(response.status_code, 200)
		return json.loads(response.content)

	@override_settings(SONADOR_VERSION='0.4.0')
	def test_release_version_is_reported(self):
		self.assertEqual(self.get_config().get('sonadorVersion'), '0.4.0')

	@override_settings(SONADOR_VERSION='dev')
	def test_unreleased_trunk_reports_dev(self):
		'''	`master` carries 'dev' rather than a number, so the viewer must pass the value through
			verbatim instead of assuming it parses as a semantic version.
		'''
		self.assertEqual(self.get_config().get('sonadorVersion'), 'dev')

	@override_settings(SONADOR_VERSION=None)
	def test_absent_version_omits_the_key_and_leaves_the_document_valid(self):
		'''	A deployment running an older settings module has no version to report. The template
			has to drop the key entirely -- an unguarded tag would emit the string "None", which
			the viewer would faithfully display as the API version.
		'''
		config = self.get_config()

		self.assertNotIn('sonadorVersion', config)

		# The rest of the document must be unaffected: the viewer cannot boot without it.
		self.assertIn('routerBasename', config)
		self.assertIn('hotkeys', config)

	def test_version_travels_with_the_rest_of_the_configuration(self):
		'''	The About panel reads the URL and the version from the same document, so a response
			carrying one but not the other would leave the panel half answered.
		'''
		with override_settings(SONADOR_VERSION='0.4.0'):
			config = self.get_config()

		self.assertEqual(config.get('sonadorVersion'), '0.4.0')
		self.assertTrue(config.get('sonadorUrl'))

	# NOTE: the imaging-server scoped variant of this endpoint (`ohif-imageserver-config`) is not
	# covered here. It shares `get_context_data` with the route above, so it reports the version by
	# the same code path, but it cannot currently be exercised: `PacsImagingServer.url_viewer`
	# reverses a URL name (`ohif-imageserver-viewer`) that no longer exists in `sonador/urls.py`,
	# so the view raises NoReverseMatch before it renders. That is a pre-existing routing defect,
	# unrelated to version reporting.
