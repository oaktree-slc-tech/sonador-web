from django.shortcuts import reverse
from django.utils.html import format_html
from django.contrib import admin

from guru.helpers import gsetting

from secure.models import ApiAccess, ApiAccessToken
from secure.admin import ApiAccessAdmin, ApiAccessTokenAdmin

from ..auth.models import SocialAuthorizationServer, PacsImagingServerUserAuthorization, PacsImagingServerGroupAuthorization, \
	DataService
from ..models import PacsImagingServer, DicomImagingModality, RemoteDICOMwebServer 

from .auth import ProxyApiAccess, ProxyApiAccessToken, ProxySecureSocialAuthorizationServer, SocialAuthorizationServerAdmin, \
	ProxyDataService, DataServiceAdmin
from .servers import PacsImagingServerAdmin, ImagingServerAdminMixin, DicomImagingModalityAdmin, RemoteDICOMWebServerAdmin


# Authorization and authentication
if gsetting('AUTH_ENABLED'):
	admin.site.register(ProxyApiAccessToken, ApiAccessTokenAdmin)
	admin.site.register(ProxySecureSocialAuthorizationServer, SocialAuthorizationServerAdmin)
	admin.site.register(ProxyApiAccess, ApiAccessAdmin)
	admin.site.register(ProxyDataService, DataServiceAdmin)


admin.site.register(PacsImagingServer, PacsImagingServerAdmin)
admin.site.register(DicomImagingModality, DicomImagingModalityAdmin)
admin.site.register(RemoteDICOMwebServer, RemoteDICOMWebServerAdmin)
