import guru.forms as guru_forms


class SonadorBaseForm(guru_forms.GuruCoreForm):
	'''	Core form class used for managing Sonador Imaging resources
	'''
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		for fname, field in self.fields.items():

			# Add default/initial values to data for required fields which may not 
			# have been provided with the form data.
			if field.required and field.initial and not self.data.get(fname):
				self.data[fname] = field.initial