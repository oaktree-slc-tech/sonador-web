from django import forms
from django.shortcuts import reverse
from django.utils.html import format_html
from django.contrib import admin

from guru.helpers import gsetting
from guru.helpers.user import user_displayname

from secure.models import ApiAccess, ApiAccessToken
from secure.admin import ApiAccessAdmin, ApiAccessTokenAdmin

from content.widgets import CodeEditorAdminWidget

from ..auth.models import SocialAuthorizationServer, PacsImagingServerUserAuthorization, PacsImagingServerGroupAuthorization, \
	DataService
from ..models import PacsImagingServer, DicomImagingModality, RemoteDICOMwebServer 
from ..models.branding import SonadorSite
from ..apisettings.display_attrs import SERIES_TAG_TOOL, DISPLAY_ATTRIBUTE_COLOR, DISPLAY_COLOR_ROLES, \
	site_display_attributes, normalize_hex_color

from .auth import SonadorApiAccess, SonadorApiAccessToken, ProxySecureSocialAuthorizationServer, \
	SocialAuthorizationServerSearchAdmin, SocialAuthorizationServerAdmin, \
	ProxyDataService, DataServiceAdmin
from .servers import PacsImagingServerAdmin, ImagingServerAdminMixin


# API Management

class UserLabelMixin(object):
	search_fields = ('user__username', 'user__first_name', 'user__last_name', 'user__email')
	autocomplete_fields = ('user',)

	@admin.display(
	    description=''
	)
	def user_display(self, obj):
		return user_displayname(obj.user)

	@admin.display(
	    description='Email'
	)
	def user_email(self, obj):
		return obj.user.email


@admin.register(SonadorApiAccessToken)
class SonadorApiAccessTokenAdmin(UserLabelMixin, ApiAccessTokenAdmin):
	'''	Admin to manage API tokens within Sonador
	'''
	list_display = ('user', 'user_display', 'user_email', 'admin_masked_token', 'description', 'ctime')


@admin.register(SonadorApiAccess)
class SonadorApiAccessAdmin(UserLabelMixin, ApiAccessAdmin):
	'''	Admin to manage API access IDs and secrets within Sonador
	'''
	list_display = ('user', 'user_display', 'user_email', 'admin_masked_access_id', 'description', 'ctime')


# Site Management


# Markdown message fields on SonadorSite which are edited with the ACE code editor
SONADORSITE_MARKDOWN_FIELDS = ('welcome', 'farewell')


# Series Tag color fields on the site form: (form field, color role)
SONADORSITE_SERIES_TAG_COLOR_FIELDS = tuple(('series_tag_color_%s' % role.lower(), role) for role in DISPLAY_COLOR_ROLES)

SERIES_TAG_COLOR_HELP = {
	'Background': 'Fill behind the tag. Leave blank for no fill.',
	'Border': 'Outline of the tag. Leave blank to use the built-in default (white).',
	'Value': 'Text color of the coded concept value. Leave blank to use the built-in default.',
	'Meaning': 'Text color of the code meaning. Leave blank to use the built-in default.',
}


class HexColorWidget(forms.TextInput):
	'''	Text input for a `#RRGGBB` color with a native color picker alongside it
	'''
	template_name = 'admin/widgets/hex_color.html'

	def __init__(self, attrs=None):
		super().__init__(attrs={ 'placeholder': '#RRGGBB', 'size': 9, 'maxlength': 7, **(attrs or {}) })


class SonadorSiteAdminForm(forms.ModelForm):
	'''	ModelAdmin form which provides an ACE text editor for the site's markdown messages
		("Welcome" and "Farewell") and color fields for the Series Tag display attribute defaults.
	'''
	series_tag_color_background = forms.CharField(label='Background Color', required=False, widget=HexColorWidget(),
		help_text=SERIES_TAG_COLOR_HELP['Background'])
	series_tag_color_border = forms.CharField(label='Border Color', required=False, widget=HexColorWidget(),
		help_text=SERIES_TAG_COLOR_HELP['Border'])
	series_tag_color_value = forms.CharField(label='Value Color', required=False, widget=HexColorWidget(),
		help_text=SERIES_TAG_COLOR_HELP['Value'])
	series_tag_color_meaning = forms.CharField(label='Meaning Color', required=False, widget=HexColorWidget(),
		help_text=SERIES_TAG_COLOR_HELP['Meaning'])

	class Meta:
		model = SonadorSite
		exclude = ('display_attributes',)
		widgets = { field: CodeEditorAdminWidget(code_language='markdown') for field in SONADORSITE_MARKDOWN_FIELDS }

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		for field in SONADORSITE_MARKDOWN_FIELDS:
			self.fields[field].widget.attrs.update({ CodeEditorAdminWidget.code_language_attr: 'markdown' })

		color = site_display_attributes(self.instance).get(SERIES_TAG_TOOL, {}).get(DISPLAY_ATTRIBUTE_COLOR, {})
		for field, role in SONADORSITE_SERIES_TAG_COLOR_FIELDS:
			self.initial.setdefault(field, color.get(role) or '')

	def clean(self):
		cleaned_data = super().clean()
		for field, role in SONADORSITE_SERIES_TAG_COLOR_FIELDS:
			try:
				cleaned_data[field] = normalize_hex_color(cleaned_data.get(field))
			except forms.ValidationError as err:
				self.add_error(field, err)
		return cleaned_data

	def save(self, commit=True):
		display_attributes = site_display_attributes(self.instance)
		display_attributes[SERIES_TAG_TOOL] = { DISPLAY_ATTRIBUTE_COLOR: {
			role: self.cleaned_data.get(field) for field, role in SONADORSITE_SERIES_TAG_COLOR_FIELDS } }
		self.instance.display_attributes = display_attributes
		return super().save(commit=commit)


@admin.register(SonadorSite)
class SonadorSitesAdmin(admin.ModelAdmin):
	'''	Model admin instance for managing Sonador site instances	
	'''
	list_display = ('id', 'name', 'domain')

	fieldsets = (
		('Site Properties', { 'fields': ('name', 'domain')}),
		('Site Branding', { 'fields': ('logo', 'logo_narrow', 'favicon', 'welcome', 'farewell')}),
		('Display Attributes: Series Tags', {
			'fields': tuple(field for field, role in SONADORSITE_SERIES_TAG_COLOR_FIELDS),
			'description': 'Default colors of Series Tags rendered in the viewer. A tag\'s own display attributes take precedence.',
		}),
	)

	form = SonadorSiteAdminForm


# Authorization and authentication
admin.site.register(SocialAuthorizationServer, SocialAuthorizationServerSearchAdmin)
admin.site.register(ProxySecureSocialAuthorizationServer, SocialAuthorizationServerAdmin)
admin.site.register(ProxyDataService, DataServiceAdmin)


# Site admin (replaces built-in Django Site Admin)


admin.site.register(PacsImagingServer, PacsImagingServerAdmin)
