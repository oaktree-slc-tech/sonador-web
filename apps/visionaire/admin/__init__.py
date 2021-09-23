from django.shortcuts import reverse
from django.utils.html import format_html
from django.contrib import admin

from guru.helpers import gsetting

from secure.models import ApiAccess, ApiAccessToken
from secure.admin import ApiAccessAdmin, ApiAccessTokenAdmin

from ..auth.models import SocialAuthorizationServer, PacsImagingServerUserAuthorization, PacsImagingServerGroupAuthorization
from ..models import PacsImagingServer, DicomImagingModality, RemoteDICOMwebServer 

from .auth import ProxyApiAccess, ProxyApiAccessToken, ProxySecureSocialAuthorizationServer, SocialAuthorizationServerAdmin, \
	ProxyPacsImagingServerGroupAuthorization, PacsImagingGroupAuthorizationAdmin
from .servers import PacsImaginServerAdmin, ImagingServerAdminMixin, DicomImagingModalityAdmin, RemoteDICOMWebServerAdmin


# Authorization and authentication
if gsetting('AUTH_ENABLED'):
	admin.site.register(ProxyApiAccessToken, ApiAccessTokenAdmin)
	admin.site.register(ProxySecureSocialAuthorizationServer, SocialAuthorizationServerAdmin)
	admin.site.register(ProxyApiAccess, ApiAccessAdmin)
	admin.site.register(ProxyPacsImagingServerGroupAuthorization, PacsImagingGroupAuthorizationAdmin)


admin.site.register(PacsImagingServer, PacsImaginServerAdmin)
admin.site.register(DicomImagingModality, DicomImagingModalityAdmin)
admin.site.register(RemoteDICOMwebServer, RemoteDICOMWebServerAdmin)
