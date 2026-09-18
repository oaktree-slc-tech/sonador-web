'''	Tests for the identity provider admin change page.

	The page is saved by the Backbone admin scripts rather than a form POST: each control's
	value is read into a model which is PUT back to the admin API as JSON. A checkbox has no
	value of its own and reports "on" whether or not it is ticked, so the login protection
	toggles are rendered as enabled/disabled selects whose value is the state.
'''
import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from wgtauth.social.models import SocialAppProvider

from . import fixtures


PROTECTION_FIELDS = ('oidc_state', 'oidc_pkce', 'oidc_nonce', 'oidc_id_token_required')


class ProviderAdminTests(TestCase):

	def setUp(self):
		self.provider = fixtures.create_authserver().provider
		# The change form requires the login control class the shared fixture leaves blank
		SocialAppProvider.objects.filter(pk=self.provider.pk).update(login_class='btn-idp')
		self.provider.refresh_from_db()
		self.client.force_login(User.objects.create_superuser('admin', 'admin@example.com', 'secret'))
		self.url_change = reverse('admin:wgtsocial_socialappprovider_change', args=(self.provider.pk,))
		self.url_update = reverse('admin:wgtsocial-socialappprovider-apiupdate', args=(self.provider.pk,))

	def update(self, **fields):
		'''	Send the values the change page would read from its controls
		'''
		response = self.client.put(self.url_update, data=json.dumps(fields), content_type='application/json')
		self.assertEqual(response.status_code, 200, response.content)
		return SocialAppProvider.objects.get(pk=self.provider.pk)

	def test_the_protection_toggles_are_selects_rather_than_checkboxes(self):
		page = self.client.get(self.url_change).content.decode()
		for fieldname in PROTECTION_FIELDS:
			self.assertIn('<select name="%s"' % fieldname, page)
			self.assertNotIn('type="checkbox" name="%s"' % fieldname, page)

	def test_the_selects_carry_the_current_state(self):
		SocialAppProvider.objects.filter(pk=self.provider.pk).update(oidc_pkce=False, oidc_id_token_required=True)
		form = self.client.get(self.url_change).context['adminform'].form
		self.assertEqual(form['oidc_pkce'].value(), False)
		self.assertEqual(form['oidc_id_token_required'].value(), True)
		self.assertIn('<option value="False" selected>', str(form['oidc_pkce']))
		self.assertIn('<option value="True" selected>', str(form['oidc_id_token_required']))

	def test_each_protection_can_be_disabled_and_enabled_from_the_page(self):
		provider = self.update(oidc_state='False', oidc_pkce='False', oidc_nonce='False', oidc_id_token_required='True')
		self.assertEqual([getattr(provider, name) for name in PROTECTION_FIELDS], [False, False, False, True])

		provider = self.update(oidc_state='True', oidc_pkce='True', oidc_nonce='True', oidc_id_token_required='False')
		self.assertEqual([getattr(provider, name) for name in PROTECTION_FIELDS], [True, True, True, False])

	def test_other_fields_are_untouched_by_a_toggle_update(self):
		provider = self.update(oidc_nonce='False')
		self.assertEqual(provider.name, self.provider.name)
		self.assertEqual(provider.endpoint_token, self.provider.endpoint_token)
		self.assertTrue(provider.oidc_state)
