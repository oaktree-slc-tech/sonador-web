import logging, posixpath

from django.db import models
from django.core import signing
from django.utils.text import slugify

from guru.models import GuruTokenModel
from guru.helpers import gsetting, create_token
from guru.helpers.utils.object import pick, omit

from secure.fields import EncryptedCharField

from microservices.models import BaseServerModel
from microservices.control import server_controlurl, \
	server_controloperation_put, server_controloperation_delete


class OrthancPropertiexMixin(object):

	@property
	def orthanc_name(self):
		'''	Identifier used for the modality within Orthancs
		'''
		return slugify(self.name)



class OrthancImagingModalityBaseModel(OrthancPropertiexMixin, GuruTokenModel):
	'''	Remote DICOM modality associated with a Sonador managed object. Supports
		permissions to connect, query, and retrieve data.
	'''
	name = models.CharField(verbose_name='Modality Name', max_length=32, default=create_token,
		help_text='Name by which the modality will be referred to within Orthanc.')
	aet = models.CharField(verbose_name='AET', max_length=17,
		help_text='Application Entity Title of the DICOM instance')
	port = models.IntegerField(verbose_name='Port',
		help_text='Port number of the modality instance')
	host = models.CharField(verbose_name='Host', max_length=32,
		help_text='IP Address of the modality')

	acl_allow_echo = models.BooleanField(verbose_name='Respond to Echo Requests', default=True,
		help_text='Allow the modality to send an "echo" request to the server. ' \
			+ 'Echo requests are used to test connectivity between two DCM instances.')
	acl_allow_find = models.BooleanField(verbose_name='Allow Metadata Find Requests (C-Find)', default=True,
		help_text='Allow the modality to query the server using C-Find requests and fetch image metadata.')
	acl_allow_get = models.BooleanField(verbose_name='Allow Get Requests (C-GET)', default=True,
		help_text='Allow the modality to retrieve images using the C-GET protocol.')
	acl_allow_move = models.BooleanField(verbose_name='Allow Query/Retrieve (C-Move)', default=True,
		help_text='Allow the modality to initialize DICOM "move" requests (C-MOVE) to retrieve image data.')
	acl_allow_store = models.BooleanField(verbose_name='Allow Modality to Write Data (C-Store)', default=True,
		help_text='Allow the modality to send data to the imaging server.')

	class Meta:
		abstract = True

	