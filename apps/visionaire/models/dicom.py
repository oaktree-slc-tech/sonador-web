import logging, posixpath

from django.db import models
from django.core import signing
from django.utils.text import slugify

from guru.models import GuruTokenModel
from guru.helpers import gsetting, create_token
from guru.helpers.utils.object import pick, omit

from secure.fields import EncryptedCharField

from core.models import OrthancPropertiexMixin, OrthancImagingModalityBaseModel

from microservices.models import BaseServerModel
from microservices.control import server_controlurl, \
	server_controloperation_put, server_controloperation_delete

from ..helpers import API_ACCESS_SERVER_TOKEN

from .servers import PacsImagingServer

logger = logging.getLogger(__name__)


class DicomImagingModality(OrthancImagingModalityBaseModel):
	'''	Remote DICOM instance associated with a PACS server instance which is able
		to connect, query, and retrieve data.
	'''
	server = models.ForeignKey(PacsImagingServer, on_delete=models.CASCADE,
		help_text='Imaging server the modality is associated with.')

	class Meta:
		app_label = 'visionaire'
		verbose_name = 'DICOM Imaging Modality'
		verbose_name_plural = 'DICOM Modalities'
		ordering = ('server', 'name')

	def save(self, *args, **kwargs):
		'''	Save configuration changes to Orthanc, persist to local database
		'''
		# Send changes to Orthanc
		rdata = server_controloperation_put(self.server.control, 
			{ 'AET': self.aet, 'Port': self.port, 'Host': self.host,
				'AllowEcho': self.acl_allow_echo, 'AllowFind': self.acl_allow_find,
				'AllowGet': self.acl_allow_get, 'AllowMove': self.acl_allow_move, 'AllowStore': self.acl_allow_store }, 
			resource=posixpath.join('modalities', self.orthanc_name), 
			headers=self.server.sonador_auth, parse_response=False)
		
		return super(DicomImagingModality, self).save(*args, **kwargs)

	def delete(self, *args, **kwargs):
		'''	Save configuration changes to Orthanc, remove from local database
		'''
		# Remove from Orthanc
		rdata = server_controloperation_delete(self.server.control,
			resource=posixpath.join('modalities', self.orthanc_name),
			headers=self.server.sonador_auth, parse_response=False)

		return super(DicomImagingModality, self).delete(*args, **kwargs)

	def __str__(self, *args, **kwargs):
		return '%s: %s' % (self.pk, self.name)

	@property
	def json(self):
		odata = { 'server': self.server.pk, 'orthanc_name': self.orthanc_name, }
		odata.update(pick(self, ('token', 'name', 'aet', 'port', 'host', 
			'acl_allow_echo', 'acl_allow_find', 'acl_allow_get', 'acl_allow_move', 'acl_allow_store')))
		return odata



class RemoteDICOMwebServer(OrthancPropertiexMixin, BaseServerModel):
	'''	Remote DICOMweb instance associated with a PACS server instance which is able
		to connect, query, and retrieve data.
	'''
	server = models.ForeignKey(PacsImagingServer, on_delete=models.CASCADE,
		help_text='Imaging server the modality is associated with.')
	username = EncryptedCharField('Remote Username', max_length=256)
	password = EncryptedCharField('Remote Server Password', max_length=1024,
		help_text='Password for the remote server user.')

	dicomweb_urlroot = 'dicom-web/'

	class Meta:
		app_label = 'visionaire'
		verbose_name = 'Remote DICOMweb Server '
		verbose_name_plural = 'DICOMweb Servers'
		ordering = ('server', 'name')

	def save(self, *args, **kwargs):
		'''	Save configuration changes to Orthanc, persist to local database
		'''
		# Send changes to Orthanc
		rdata = server_controloperation_put(self.server.control, 
			{ 'Url': server_controlurl(self, 'dicom-web/'), 'Username': self.username, 'Password': self.password, }, 
			resource=posixpath.join('dicom-web', 'servers', self.orthanc_name), 
			headers=self.server.sonador_auth, parse_response=False)
		
		return super(RemoteDICOMwebServer, self).save(*args, **kwargs)

	def delete(self, *args, **kwargs):
		'''	Save configuration changes to Orthanc, remove from local database
		'''
		# Remove from Orthanc
		rdata = server_controloperation_delete(self.server.control,
			resource=posixpath.join('dicom-web', 'servers', self.orthanc_name), 
			headers=self.server.sonador_auth, parse_response=False)

		return super(RemoteDICOMwebServer, self).delete(*args, **kwargs)

	def __str__(self, *args, **kwargs):
		return '%s: %s' % (self.pk, self.name)

	@property
	def json(self):
		odata = { 'server': self.server.pk, 'dicomweb_url': server_controlurl(self, self.dicomweb_urlroot), 'orthanc_name': self.orthanc_name, }
		odata.update(pick(self, [f.name for f in self._meta.fields if not f.name in odata]))
		return omit(odata, ('default',))
