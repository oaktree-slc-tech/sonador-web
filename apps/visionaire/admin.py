from django.contrib import admin
from .auth.models import SocialAuthorizationServer


class SocialAuthorizationServerAdmin(admin.ModelAdmin):
    list_display = ('token', 'provider', 'description', 'url_login', 'url_callback')


admin.site.register(SocialAuthorizationServer, SocialAuthorizationServerAdmin)

