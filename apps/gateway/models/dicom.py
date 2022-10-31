from django.db import models
from django.core import signing

from guru.helpers.utils.object import pick

from core.models import OrthancPropertiexMixin, OrthancImagingModalityBaseModel

from .devices import ClinicalGateway


class GatewayDicomImagingModality(OrthancImagingModalityBaseModel):
	'''	DICOM instance within the same network as a clinical gateway which is authorized
		to connect to the gateway instance, query, and retrieve data.
	'''
	gateway = models.ForeignKey(ClinicalGateway, on_delete=models.CASCADE,
		help_text='Clinical gateway the modality is associated with.')

	class Meta:
		app_label = 'gateway'
		verbose_name = 'DICOM Imaging Modality'
		verbose_name_plural = 'DICOM Modalities'
		ordering = ('gateway', 'name')

	@property
	def json(self):
		odata = { 'gateway': self.gateway.pk, 'orthanc_name': self.orthanc_name, }
		odata.update(pick(self, ('token', 'name', 'aet', 'port', 'host', 
			'acl_allow_echo', 'acl_allow_find', 'acl_allow_get', 'acl_allow_move', 'acl_allow_store')))
		return odata