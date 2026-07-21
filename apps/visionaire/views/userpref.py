from django.db import transaction

from guru.views import GuruApiDetailsMixin, GuruApiCreateView
from guru.helpers import operation_results

from core.views import JSONFormApiView

from ..models.userpref import UserPref, CURRENT_PREF_VERSION
from ..forms.userpref import UserPrefForm


# Model JSON fields the section endpoints write into (AR-4 `field` selector).
VIEWER_FIELD = 'viewer'
STUDYLIST_FIELD = 'studylist'


class UserPrefApiManagementView(GuruApiDetailsMixin, GuruApiCreateView):
	'''	API REST view for User Prefs managed by Sonador.

		Retained for backward compatibility (FR-5): GET returns the full preference
		document (`viewer` + `studylist`) and POST accepts a whole-document write via
		the reworked (now user-bound, optional-field) UserPrefForm. Section-scoped
		writes should use UserPrefSectionApiView.
	'''
	model = UserPref
	modelform = UserPrefForm

	def getObject(self, request, *args, objectid=None, **kwargs):
		model,created =  self.model.objects.get_or_create(user=self.request.user)
		return model

	def get(self, request, *args, **kwargs):
		return super().get(request, *args, objectid=None, **kwargs)


class UserPrefSectionApiView(JSONFormApiView):
	'''	Generic section-scoped preferences API view (AR-4). One class configured per
		section via as_view():

		- `section` (str): key inside the version document (`general`, `hotkeys`,
		  `windowLevel`, `viewerMetadata`). Ignored when `field` is `studylist`, whose
		  version document is itself the interface map (FR-14).
		- `formclass`: section form validating the `{ version, values }` body.
		- `field` (str): model JSON field written -- `viewer` (default) or `studylist`.

		GET  -> `{ "version": <v>, "values": {...} }` for `?version=` (default 0.4),
		        `values` empty when nothing is stored (FR-3).
		POST -> validates `values` with `formclass` and persists under `[version][section]`
		        (viewer) or merges interfaces under `[version]` (studylist, FR-14). The
		        read-modify-write runs inside `transaction.atomic()` with the row locked
		        via `select_for_update()` (FR-6). Validation failures return 400 with the
		        guru form-error envelope and write nothing (FR-4).

		Responses use the guru results envelope; clients read the payload from `results`.
	'''
	section = None
	formclass = None
	field = VIEWER_FIELD

	def resolve_version(self, request):
		'''	Requested version, defaulting to the current release (FR-3).
		'''
		return request.GET.get('version', CURRENT_PREF_VERSION)

	def section_results(self, version, values):
		'''	Wrap `{ version, values }` in the guru results envelope.
		'''
		return operation_results({'results': {'version': version, 'values': values}})

	def get(self, request, *args, **kwargs):
		version = self.resolve_version(request)

		# Mirror the existing management view: every authenticated user implicitly
		# owns a row (get_or_create).
		userpref, created = UserPref.objects.get_or_create(user=request.user)

		if self.field == STUDYLIST_FIELD:
			# The studylist version document is the full interface map (FR-13).
			values = userpref.get_section(STUDYLIST_FIELD, version, section=None)
		else:
			values = userpref.get_section(self.field, version, self.section)

		return self.section_results(version, values)

	def post(self, request, *args, **kwargs):
		form = self.get_form()
		if not form.is_valid():
			# 400 + guru form-error envelope; nothing written (FR-4).
			return self.form_invalid(form)

		version = form.cleaned_data['version']
		values = form.cleaned_data['values']

		# FR-6: read-modify-write the JSON document under a row lock so concurrent
		# section/interface writes cannot clobber one another.
		with transaction.atomic():
			UserPref.objects.get_or_create(user=request.user)
			userpref = UserPref.objects.select_for_update().get(user=request.user)

			if self.field == STUDYLIST_FIELD:
				stored = userpref.merge_interfaces(version, values)
			else:
				stored = userpref.set_section(self.field, version, self.section, values)

			userpref.save(update_fields=[self.field])

		return self.section_results(version, stored)
