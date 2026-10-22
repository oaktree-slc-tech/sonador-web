'''	Site display attribute defaults: validation, the Site admin editor, and the read-only `site`
	key of the whole-document user-preferences response.
'''
import json

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase, override_settings

from ..admin import SonadorSiteAdminForm
from ..apisettings.display_attrs import SERIES_TAG_TOOL, clean_display_attributes, default_display_attributes, normalize_hex_color
from ..models.branding import SonadorSite
from ..models.userpref import UserPref
from ..views.userpref import UserPrefApiManagementView


SERIES_TAG_DEFAULTS = { SERIES_TAG_TOOL: { 'Color': { 'Background': None, 'Border': '#FFFFFF', 'Value': '#8AD0A8', 'Meaning': '#C0C7F8' } } }


class DisplayAttributeValidationTests(TestCase):

	def test_colors_are_normalized(self):
		self.assertEqual(normalize_hex_color('#8ad0a8'), '#8AD0A8')
		self.assertEqual(normalize_hex_color('#fff'), '#FFFFFF')
		self.assertIsNone(normalize_hex_color(''))
		self.assertIsNone(normalize_hex_color(None))

	def test_invalid_colors_are_refused(self):
		for value in ('8AD0A8', '#8AD0A', 'green', '#8AD0A8FF', 12):
			with self.assertRaises(ValidationError, msg=value):
				normalize_hex_color(value)

	def test_document_is_normalized(self):
		self.assertEqual(
			clean_display_attributes({ SERIES_TAG_TOOL: { 'Color': { 'Value': '#abc', 'Background': None } } }),
			{ SERIES_TAG_TOOL: { 'Color': { 'Background': None, 'Value': '#AABBCC' } } })

	def test_unknown_tools_and_keys_are_refused(self):
		for value in (
			{ 'LengthTool': { 'Color': {} } },
			{ SERIES_TAG_TOOL: { 'Font': 'Arial' } },
			{ SERIES_TAG_TOOL: { 'Color': { 'Outline': '#FFFFFF' } } },
			{ SERIES_TAG_TOOL: { 'Color': { 'Border': 'white' } } },
			{ SERIES_TAG_TOOL: { 'Color': { 'Value': 'green' } } },
			{ SERIES_TAG_TOOL: { 'Color': [] } },
			{ SERIES_TAG_TOOL: { 'Color': False } },
			{ SERIES_TAG_TOOL: { 'Color': 0 } },
			{ SERIES_TAG_TOOL: { 'Color': '' } },
			[SERIES_TAG_TOOL],
			'',
		):
			with self.assertRaises(ValidationError, msg=value):
				clean_display_attributes(value)

	def test_absent_or_null_color_is_an_empty_document(self):
		self.assertEqual(clean_display_attributes({ SERIES_TAG_TOOL: {} }), { SERIES_TAG_TOOL: { 'Color': {} } })
		self.assertEqual(clean_display_attributes({ SERIES_TAG_TOOL: { 'Color': None } }), { SERIES_TAG_TOOL: { 'Color': {} } })

	def test_a_new_site_carries_the_built_in_defaults(self):
		site = SonadorSite.objects.create(domain='defaults.example.com', name='Defaults')
		self.assertEqual(site.display_attributes, SERIES_TAG_DEFAULTS)
		self.assertEqual(default_display_attributes(), SERIES_TAG_DEFAULTS)


class SiteAdminFormTests(TestCase):

	def form(self, site, **colors):
		data = { 'name': site.name, 'domain': site.domain }
		data.update({ 'series_tag_color_%s' % role: value for role, value in colors.items() })
		return SonadorSiteAdminForm(data=data, instance=site)

	def test_initial_values_come_from_the_site(self):
		site = SonadorSite.objects.create(domain='form.example.com', name='Form')
		form = SonadorSiteAdminForm(instance=site)
		self.assertEqual((form.initial['series_tag_color_background'], form.initial['series_tag_color_border'],
			form.initial['series_tag_color_value'], form.initial['series_tag_color_meaning']), ('', '#FFFFFF', '#8AD0A8', '#C0C7F8'))

	def test_save_writes_normalized_colors(self):
		site = SonadorSite.objects.create(domain='save.example.com', name='Save')

		form = self.form(site, background='#123', border='#0f0', value='#ff0000', meaning='')
		self.assertTrue(form.is_valid(), form.errors)
		form.save()

		site.refresh_from_db()
		self.assertEqual(site.display_attributes,
			{ SERIES_TAG_TOOL: { 'Color': { 'Background': '#112233', 'Border': '#00FF00', 'Value': '#FF0000', 'Meaning': None } } })

	def test_invalid_color_is_reported_on_its_field(self):
		site = SonadorSite.objects.create(domain='invalid.example.com', name='Invalid')

		form = self.form(site, background='', border='', value='green', meaning='#C0C7F8')
		self.assertFalse(form.is_valid())
		self.assertIn('series_tag_color_value', form.errors)

		site.refresh_from_db()
		self.assertEqual(site.display_attributes, SERIES_TAG_DEFAULTS)


class UserPrefSiteKeyTests(TestCase):

	def setUp(self):
		self.factory = RequestFactory()
		self.user = User.objects.create_user('ines.vaz', password='x')
		self.site = SonadorSite.objects.create(domain='prefs.example.com', name='Prefs')

	def dispatch(self, request):
		request.user = self.user
		with override_settings(SITE_ID=self.site.pk):
			return UserPrefApiManagementView.as_view()(request)

	def get(self):
		response = self.dispatch(self.factory.get('/visionaire/api/user-preferences/'))
		self.assertEqual(response.status_code, 200)
		return json.loads(response.content)

	def test_get_includes_the_site_defaults(self):
		self.assertEqual(self.get()['site'], { 'displayAttributes': SERIES_TAG_DEFAULTS })

	def test_get_reflects_the_sites_own_values(self):
		self.site.display_attributes = { SERIES_TAG_TOOL: { 'Color': { 'Background': '#000000', 'Value': '#FFFFFF', 'Meaning': None } } }
		self.site.save()
		self.assertEqual(self.get()['site']['displayAttributes'][SERIES_TAG_TOOL]['Color']['Background'], '#000000')

	def test_model_stores_canonical_colors(self):
		self.site.display_attributes = { SERIES_TAG_TOOL: { 'Color': { 'Background': '#abc', 'Value': '#ff0000' } } }
		self.site.full_clean()
		self.site.save()

		expected = { SERIES_TAG_TOOL: { 'Color': { 'Background': '#AABBCC', 'Value': '#FF0000' } } }
		self.site.refresh_from_db()
		self.assertEqual(self.site.display_attributes, expected)
		self.assertEqual(self.get()['site']['displayAttributes'], expected)

	def test_model_refuses_an_invalid_document(self):
		self.site.display_attributes = { SERIES_TAG_TOOL: { 'Color': [] } }
		with self.assertRaises(ValidationError):
			self.site.full_clean()
		with self.assertRaises(ValidationError):
			self.site.save()

	def test_site_without_a_stored_document_falls_back_to_the_defaults(self):
		SonadorSite.objects.filter(pk=self.site.pk).update(display_attributes={})
		self.assertEqual(self.get()['site'], { 'displayAttributes': SERIES_TAG_DEFAULTS })

	def test_post_ignores_site(self):
		body = { 'viewer': { '0.4': { 'general': { 'language': 'en-US' } } },
			'site': { 'displayAttributes': { SERIES_TAG_TOOL: { 'Color': { 'Value': '#000000' } } } } }
		self.dispatch(self.factory.post('/visionaire/api/user-preferences/', data=json.dumps(body), content_type='application/json'))

		self.assertEqual(UserPref.objects.get(user=self.user).viewer, body['viewer'])
		self.site.refresh_from_db()
		self.assertEqual(self.site.display_attributes, SERIES_TAG_DEFAULTS)
		self.assertNotIn('site', [f.name for f in UserPref._meta.get_fields()])
		self.assertEqual(self.get()['site'], { 'displayAttributes': SERIES_TAG_DEFAULTS })
