from django import forms

from guru.filter.forms import GuruFilterForm
from guru.filter.views import GuruQueryParamFilterFormMixin

from ...views.dicom import PacsImagingServerChildObjectManagementView, PacsImagingServerChildObjectRestView

from ..models import PacsImagingServerGroupAuthorization
from ..forms.acl import PacsImagingServerGroupAuthorizationForm



class PacsImagingServerGroupAuthorizationFilterForm(GuruFilterForm):
	'''	Filter form which can be used to search for group authorization policy instances
	'''
	group = forms.CharField(max_length=256, required=False)

	filterkey_transforms = {
		'group': 'group__name',
	}


class PacsImagingServerGroupAuthorizationManagementView(GuruQueryParamFilterFormMixin, PacsImagingServerChildObjectManagementView):
	'''	View class for managing group authorization policies for an imaging server
	'''
	model = PacsImagingServerGroupAuthorization
	modelform = PacsImagingServerGroupAuthorizationForm
	filterform = PacsImagingServerGroupAuthorizationFilterForm

	response_objectid_fieldname = 'token'


class PacsImagingServerGroupAuthorizationRestView(PacsImagingServerChildObjectRestView):
	'''	View class for managing specific group authorization policy instances for an imaging server
	'''
	model = PacsImagingServerGroupAuthorization
	modelform = PacsImagingServerGroupAuthorizationForm

	response_objectid_fieldname = 'token'