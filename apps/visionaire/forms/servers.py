from django import forms

from core.forms import SonadorBaseForm

from ..models.servers import PacsImagingServer, \
	DICOM_IMAGE_WADO, WADO_ROOT, DICOMWEB_ROOT, QIDO_SUPPORTS_INCLUDE_DEFAULT


class PacsImagingServerForm(SonadorBaseForm):
	'''	Form class for creating and updating Sonador Imaging Servers
	'''
	uid = forms.CharField(label='Server ID', required=False, 
		help_text='Unique ID to be used for the server. (Only available when creating a server instance.)')

	class Meta:
		model = PacsImagingServer
		fields = '__all__'

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		# If the form is being used to update a server instance, remove "uid" field to prevent
		# the server ID from being changed.
		if getattr(self, 'instance', None) and self.instance.pk:
			self.fields.pop('uid')

	def save(self, *args, **kwargs):
		'''	Save the data associated with the form.
		'''
		commit = kwargs.pop('commit', True)
		instance = super().save(*args, **kwargs,
			commit=False if not self.instance.pk and self.cleaned_data.get('uid') else commit)

		# Server ID provided in request data
		if not instance.pk and self.cleaned_data.get('uid'):
			instance.pk = self.cleaned_data.get('uid')

			if commit:
				instance.save()

		return instance
	