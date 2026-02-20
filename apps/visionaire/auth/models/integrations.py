from django.shortcuts import reverse
from django.db import models
from django.contrib.auth.models import Group

from guru.models import GuruTokenModel
from guru.helpers import gsetting
from guru.helpers.utils.object import pick, omit

from wgtauth.services.models import AbstractDataService


class DataService(AbstractDataService):
    ''' Data service associated with Sonador. Data services are able to utilize
        Sonador access credentials (API tokens, access ID/secret, and session tokens)
        for authentication via oAuth2.0 token introspection.
    '''
    authserver = models.ForeignKey('visionaire.SocialAuthorizationServer', blank=True, null=True, 
        verbose_name='Auth Server', related_name='data_services', on_delete=models.CASCADE,
        help_text='Sonador authorization server to be used by the data service. If blank, the default '
            + 'auth server for the deployment will be used.')

    class Meta:
        app_label = 'visionaire'
        ordering = ('description',)

    @property
    def url_login(self):
        ''' Login redirect endpoint (step 1 in oAuth workflow)
        '''
        return reverse('visionaire-api:data-service-openid-login', args=(self.pk,)) if self.openid_allow_auth else ''

    @property
    def url_callback(self):
        ''' Login callback endpoint (step 2 in oAuth workflow)
        '''
        return reverse('visionaire-api:data-service-openid-login-callback', args=(self.pk,)) if self.openid_allow_auth else ''

    @property
    def url_oidc_token_auth(self):
        ''' OIDC token authorization endpoint for oAuth workflows
        '''
        return reverse('visionaire-api:data-service-openid-token', args=(self.pk,)) if self.openid_allow_auth else ''
    