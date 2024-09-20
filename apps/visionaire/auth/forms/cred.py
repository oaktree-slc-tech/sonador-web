from guru.forms import create_modelform_class
from core.forms import SonadorBaseForm

from ...admin.auth import SonadorApiAccess, SonadorApiAccessToken



# Form classes for data validation
SonadorApiAccessTokenForm = create_modelform_class(SonadorApiAccessToken, exclude=('token', 'user',),
	base_formclass=SonadorBaseForm)
SonadorApiAccessCredentialForm = create_modelform_class(SonadorApiAccess, exclude=('access_id', 'secret', 'user'),
	base_formclass=SonadorBaseForm)

