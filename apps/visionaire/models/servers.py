import logging

from django.db import models
from django.core import signing
from django.shortcuts import reverse

from guru.helpers import classproperty, gsetting
from guru.helpers.utils.object import pick

from secure.helpers import server_encrypt_data

from microservices.models import BaseServerModel
from microservices.control import server_controlurl

from ..helpers import API_ACCESS_SERVER_TOKEN

logger = logging.getLogger(__name__)


DICOM_IMAGE_WADO = 'wadors'
DICOM_IMAGE_CHOICES = (
	(DICOM_IMAGE_WADO, 'Wadors'),
)


def pacs_ohif_serverdata(server):
	''' Ceate a JSON dictionary of the server configuration properties
		required by OHIF
	'''
	sdata = pick(server, ('name', 'wadoUriRoot', 'qidoRoot', 'wadoRoot', 'qidoSupportsIncludeField', 
		'imageRendering', 'thumbnailRendering'))
	sdata['requestOptions'] = { 'requestFromBrowser': True }
	sdata['enableStudyLazyLoad'] = True

	return sdata


class ControlServer(object):
	'''	Helper object used to route requests to imaging servers which may be located
		within a cluster or firewall.
	'''
	def __init__(self, hostname, port, scheme):
		self.hostname = hostname
		self.port = port
		self.scheme = scheme

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

	internal_hostname = models.CharField(max_length=128, blank=True, null=True,
        help_text="Hostname for the server within cluster/firewall")
	internal_port = models.PositiveIntegerField('Internal Port', blank=True, null=True,
        default=0, help_text='Port to which control requests should be sent within the cluster/firewall')
	internal_scheme = models.CharField('Internal Control Scheme', max_length=10, blank=True, null=True,
        help_text='Connection scheme which should be used to communicate with the server within cluster/firewall (e.g., http/https)')

	class Meta:
		verbose_name = 'PACS Imaging Server'
		verbose_name_plural = 'Imaging Servers'
		ordering = ('default', 'active', 'name')

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

	def user_has_perm(self, user, resource, perm):
		''' Check that the provided user has the required permissions to access the provided resource.

			@returns True if user has the requested permission, False otherwise
		'''
		return True
	
	@classproperty
	def url_apicreate(self):
		return reverse('visionaire-api:pacs-server-management')

	@property
	def url_apiupdate(self):
		return reverse('visionaire-api:pacs-server-update', args=(self.pk,))

	@property
	def url_modality_apicreate(self):
		return reverse('visionaire-api:pacs-server-modality-management', args=(self.pk,))

	@property
	def sonador_auth(self):
		return {
			'Authorization': '%s %s' % (
				API_ACCESS_SERVER_TOKEN, signing.dumps(
					server_encrypt_data(gsetting('SERVER_APITOKEN')).decode('utf-8'))),
		}

	def __str__(self, *args, **kwargs):
		return '%s (%s:%s)' % (self.name, self.hostname, self.port)

	@property
	def control(self):
		return ControlServer(
			self.internal_hostname if self.internal_hostname else self.hostname,
			self.internal_port if self.internal_port else self.port,
			self.internal_scheme if self.internal_scheme else self.scheme)

	@property
	def json(self):
		return pick(self, [f.name for f in self._meta.fields])

	@property
	def ohif_json(self):
		return pacs_ohif_serverdata(self)
