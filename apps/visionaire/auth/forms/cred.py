from guru.forms import create_modelform_class

from ...admin.auth import SonadorApiAccess, SonadorApiAccessToken



# Form classes for data validation
SonadorApiAccessTokenForm = create_modelform_class(SonadorApiAccessToken, exclude=('token', 'user',))
SonadorApiAccessCredentialForm = create_modelform_class(SonadorApiAccess, exclude=('access_id', 'secret', 'user'))

