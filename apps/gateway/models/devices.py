import logging

from django.db import models
from django.core import signing
from django.shortcuts import reverse

from django.contrib import auth
from django.contrib.auth.models import User, Group
from django.utils.text import slugify

from guru.models import GuruTokenModel
from guru.helpers import classproperty, gsetting
from guru.helpers.utils.object import pick, omit

from secure.fields import EncryptedCharField

from secure.helpers import server_encrypt_data
from microservices.control import server_controlurl

from visionaire.models import PacsImagingServer

logger = logging.getLogger(__name__)


class ClinicalGateway(GuruTokenModel):
	'''	Sonador Clnical Gateway
	'''
	user = models.ForeignKey(auth.get_user_model(),
		verbose_name='User', related_name='clinical_gateways',
		help_text='User account the clinical gateway is associated with',
		on_delete=models.CASCADE)
	
	name = models.CharField('Gateway Name', max_length=256, blank=False,
		help_text='Name used to identify the gateway instance')
	description = models.TextField(null=True, blank=True)
	
	active = models.BooleanField(verbose_name='Active', default=True)

	json_exclude = ('user',)

	class Meta:
		unique_together = ('user', 'name')
		ordering = ('active', 'user', 'name')
		app_label = 'gateway'
		verbose_name = 'Gateway'
		verbose_name_plural = 'Clinical Gateways'

	def __str__(self, *args, **kwargs):
		return '%s: %s' %  (self.pk, self.name)

	@property
	def json(self):
		return omit(pick(self, [f.name for f in self._meta.fields]), self.json_exclude)

	def json_env(self, all_keys=False):
		'''	Retrieve environment variables for the device.

			@input all_keys (bool, default=False): when True, include all keys in the output.
				By default, only active keys are included.

			@returns dict
		'''
		env = self.env.all() if all_keys else self.env.filter(active=True)
		return dict((v.key, v.value) for v in env)



class ClinicalGatewayVariable(GuruTokenModel):
	'''	Variables store information that can be retrieved by processes running on the clinical gateway
		by making an API call from the data service.
	'''
	gateway = models.ForeignKey(ClinicalGateway, blank=False, on_delete=models.CASCADE, related_name='env',
		help_text='Clinical gateway which the variable is associated with.')
	
	key = EncryptedCharField('Variable Key', max_length=512)
	value = EncryptedCharField('Variable Value', max_length=2048)
	
	description = models.CharField(null=True, max_length=4096, blank=True)
	active = models.BooleanField(verbose_name='Active', default=True)

	class Meta:
		unique_together = ('gateway', 'key')
		app_label = 'gateway'
		verbose_name = 'Gateway Environment Variable'
		verbose_name_plural = 'Environment Variables'

	def __str__(self, *args,  **kwargs):
		return '%s/%s' % (self.gateway.name, self.key)


class GatewayImagingServer(GuruTokenModel):
	'''	Imaging serrvers conneccted with a Gateway instance
	'''
	gateway = models.ForeignKey(ClinicalGateway, blank=False, on_delete=models.CASCADE)
	server = models.ForeignKey(PacsImagingServer, blank=False, on_delete=models.CASCADE)

	username = EncryptedCharField('Server Username', max_length=256)
	password = EncryptedCharField('Server Password', max_length=1024,
		help_text='Password to be used by the gateway for the imaging server.')

	dicomweb_urlroot = 'dicom-web/'

	class Meta:
		unique_together = ('gateway', 'server')
		app_label = 'gateway'
		verbose_name = 'Gateway Server'
		verbose_name_plural = 'Imaging Servers'

	def __str__(self, *args, **kwargs):
		return '%s/%s' % (self.gateway.name, self.server.name)

	@property
	def orthanc_name(self):
		return slugify(self.server.name)

	@property
	def json(self):
		odata = {
			'gateway': self.gateway.pk,
			'server': self.server.pk,
			'dicomweb_url': server_controlurl(self.server, self.dicomweb_urlroot),
			'orthanc_name': self.orthanc_name,
		}
		odata.update(pick(self.server, ('name', 'description', 'scheme', 'hostname', 'port')))
		odata.update(pick(self, [f.name for f in self._meta.fields if not f.name in odata]))
		return odata