from django.db import models

from microservices.models import BaseServerModel
from microservices.control import server_controlurl


DICOM_IMAGE_WADO = 'wadors'
DICOM_IMAGE_CHOICES = (
	(DICOM_IMAGE_WADO, 'Wadors'),
)


class PacsImagingServer(BaseServerModel):
	'''	PACS Imaging Server
	'''
	wado_root = models.CharField(verbose_name='Wado root', max_length=512, default='wado/', 
		help_text='URL path to use as the root of the server WADO interface')
	dicomweb_root = models.CharField(verbose_name='DICOMweb root', max_length=512, default='dicom-web/',
		help_text='URL path to use as the root of the server DICOMweb interface')
	qido_supports_include = models.BooleanField(verbose_name='QIDO Includes', default=True,
		help_text='QIDO interface supports include field')
	thumbnail_rendering_method = models.CharField(verbose_name='Thumbnail Render Method', 
		max_length=64, default=DICOM_IMAGE_WADO, choices=DICOM_IMAGE_CHOICES,
		help_text='Image rendering method to use for thumbnails')
	image_rendering_method = models.CharField(verbose_name='Image Render Method', 
		max_length=64, default=DICOM_IMAGE_WADO, choices=DICOM_IMAGE_CHOICES,
		help_text='Image rendering method to use by the viewer')
	active = models.BooleanField(verbose_name='Active', default=True)

	class Meta:
		verbose_name = 'PACS Imaging Server'
		verbose_name_plural = 'Imaging Servers'

	@property
	def wadoUriRoot(self):
		return server_controlurl(self, self.wado_root)

	@property
	def qidoRoot(self):
		return server_controlurl(self, self.dicomweb_root)

	@property
	def wadoRoot(self):
		return server_controlurl(self, self.dicomweb_root)

	@property
	def qidoSupportsIncludeField(self):
		return self.qido_supports_include

	@property
	def imageRendering(self):
		return self.thumbnail_rendering_method

	@property
	def thumbnailRendering(self):
		return self.image_rendering_method

	@property
	def url_admin(self):
		return server_controlurl(self, 'app/explorer.html')

	@property
	def url_dicomweb_client(self):
		return server_controlurl(self, 'dicom-web/app/client/index.html')
