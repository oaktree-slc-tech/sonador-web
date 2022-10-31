import logging

from django import forms

from guru.filter.forms import GuruFilterForm

from core.forms import SonadorBaseForm

from .models import ClinicalGateway, GatewayDicomImagingModality, GatewayImagingServer, ClinicalGatewayVariable

logger = logging.getLogger(__name__)



class ClinicalGatewayForm(SonadorBaseForm):
	'''	Form class for creating and updating Sonador Clinical Gateway devices
	'''
	class Meta:
		model = ClinicalGateway
		exclude = ('user',)


class GatewayDeviceFilterForm(GuruFilterForm):
	'''	Filter form which can be used to filter API results
	'''
	user = forms.CharField(required=False)
	active = forms.NullBooleanField(required=False)

	filterkey_transforms = {
		'user': 'user__username',
	}
