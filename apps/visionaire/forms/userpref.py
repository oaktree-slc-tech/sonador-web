from django import forms

from core.forms import SonadorBaseForm

from ..models.userpref import UserPref

class UserPrefForm(SonadorBaseForm):
	''' Form class for creating and updating Sonador data services
	'''
	viewer = forms.JSONField(label='Viewer Preferences JSON')
	studylist = forms.JSONField(label='List Preferences JSON')

	class Meta:
		model = UserPref
		fields = '__all__'