'''	Site display attribute defaults: per-tool colors keyed by viewer tool name,
	`{ '<tool>': { 'Color': { 'Background', 'Border', 'Value', 'Meaning' } } }`. The color roles follow the
	contract shared with the imaging server and viewer; the per-tool wrapper is specific to Site
	records. Blank or null colors are unset, and unknown tools or keys are rejected.
'''
import copy, re

from django.core.exceptions import ValidationError


SERIES_TAG_TOOL = 'DICOMSRSeriesTagTool'

DISPLAY_ATTRIBUTE_COLOR = 'Color'
DISPLAY_COLOR_ROLES = ('Background', 'Border', 'Value', 'Meaning')

# Tools which accept site defaults
DISPLAY_ATTRIBUTE_TOOLS = (SERIES_TAG_TOOL,)

SERIES_TAG_DEFAULT_COLOR = { 'Background': None, 'Border': '#FFFFFF', 'Value': '#8AD0A8', 'Meaning': '#C0C7F8' }

HEX_COLOR_RE = re.compile(r'^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$')


def default_display_attributes():
	'''	Site defaults: the viewer's built-in display profile
	'''
	return { SERIES_TAG_TOOL: { DISPLAY_ATTRIBUTE_COLOR: copy.copy(SERIES_TAG_DEFAULT_COLOR) } }


def normalize_hex_color(value):
	'''	Canonical upper-case `#RRGGBB` form of a hexadecimal sRGB color. Accepts `#RGB` and
		`#RRGGBB` in any case; `None` and blank values are returned as `None` (unset).

		@raises ValidationError when the value is not a hexadecimal color
	'''
	if value is None or (isinstance(value, str) and not value.strip()):
		return None
	if not isinstance(value, str) or not HEX_COLOR_RE.match(value.strip()):
		raise ValidationError('Invalid color %(value)r, colors must be hexadecimal RGB (#RRGGBB).',
			code='invalid_color', params={ 'value': value })

	hexvalue = value.strip()[1:]
	if len(hexvalue) == 3:
		hexvalue = ''.join(c*2 for c in hexvalue)
	return '#' + hexvalue.upper()


def clean_display_attributes(value):
	'''	Validate and normalize a site display attributes document. Unknown tools and keys are
		rejected; colors are normalized to `#RRGGBB`.

		@raises ValidationError
	'''
	if value is None:
		return {}
	if not isinstance(value, dict):
		raise ValidationError('Display attributes must be an object keyed by tool name.', code='invalid')

	cleaned = {}
	for tool, attrs in value.items():
		if tool not in DISPLAY_ATTRIBUTE_TOOLS:
			raise ValidationError('Unknown tool %(tool)r.', code='invalid_tool', params={ 'tool': tool })
		if attrs is None:
			continue
		if not isinstance(attrs, dict) or set(attrs) - { DISPLAY_ATTRIBUTE_COLOR }:
			raise ValidationError('Display attributes for %(tool)s may only define "Color".',
				code='invalid', params={ 'tool': tool })

		color = attrs.get(DISPLAY_ATTRIBUTE_COLOR)
		if color is None:
			color = {}
		if not isinstance(color, dict) or set(color) - set(DISPLAY_COLOR_ROLES):
			raise ValidationError('Colors for %(tool)s may only define %(roles)s.',
				code='invalid', params={ 'tool': tool, 'roles': ', '.join(DISPLAY_COLOR_ROLES) })

		cleaned[tool] = { DISPLAY_ATTRIBUTE_COLOR: { role: normalize_hex_color(color[role]) for role in DISPLAY_COLOR_ROLES if role in color } }

	return cleaned


def site_display_attributes(ssite):
	'''	Display attribute defaults for the site, falling back to the built-in profile for a site
		without a stored document
	'''
	stored = getattr(ssite, 'display_attributes', None)
	return copy.deepcopy(stored) if stored else default_display_attributes()
