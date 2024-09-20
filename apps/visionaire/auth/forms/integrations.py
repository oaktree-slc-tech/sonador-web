import logging, six, copy, base64
from six.moves.urllib import parse as urlparse

from django import forms
from django.core import signing

from guru.errors import OperationError
from guru.helpers import gsetting, operation_results
from guru.helpers.compatability import guru_page_not_found, guru_permission_denied
from guru.helpers.urls import merge_url_querystring

from secure.models import ApiAccess, ApiAccessToken
from secure.helpers import server_decrypt_data

from wgtauth.apisettings import BASIC_AUTH_TYPE, \
	OAUTH_ACCESS_TOKEN, OAUTH_TOKEN_TYPE, OAUTH_TOKEN_TYPE_BEARER, OAUTH_EXPIRATION, \
	OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_AUTHORIZATION_CODE_RESPONSE_TYPE

from core.forms import SonadorBaseForm

from ...helpers import API_AUTHORIZATION_HEADER, SESSION_SALT, ACCESS_TOKEN_MAX_AGE, \
	API_ACCESS_SERVER_TOKEN, API_ACCESS_TOKEN_QSPARAM, API_ACCESS_APITOKEN_QSPARAM, \
	API_REFERRER_REFERER_HEADER

from .base import ServiceAuthorizationRequest, SonadorServiceAuthorizationBaseForm

logger = logging.getLogger(__name__)


from ..models import DataService


class DataServiceForm(SonadorBaseForm):
    ''' Form class for creating and updating Sonador data services
    '''
    class Meta:
        model = DataService
        fields = '__all__'
        exclude = ('token',)


class IntegrationAuthorizationForm(SonadorServiceAuthorizationBaseForm):
    ''' Form class which can be used to approve or deny authentication/authorization requests
        from systems which integrate with Sonador
    '''
    formdata_transforms = {
        'token-key': 'token_key',
        'token-value': 'token_value',
    }

    def clean(self, *args, **kwargs):
        ''' Clean data and convert parameters to the format required needed for session
            or API token authorization.
        '''
        cleaned_data = super().clean(*args, **kwargs)
        logger.debug('Authentication request data:\n%r' % cleaned_data)

        # The form validates tokens based as they would appear in an "Authorization" header.
        # Re-structure token_key and token_value so that follow the expected convetions.

        # If a bearer token was provided and the type specified as "Bearer", but not structured
        # as a Authorization header; or if an API token was provided and the type specified as "api-token";
        # re-pack values: token_key='Authorization' token_value='Bearer ...' or token_value='api-token ...'
        if (cleaned_data.get('token_key') == OAUTH_TOKEN_TYPE_BEARER
                and not OAUTH_TOKEN_TYPE_BEARER in cleaned_data.get('token_value')) \
            or (cleaned_data.get('token_key') == API_ACCESS_APITOKEN_QSPARAM
                and not API_ACCESS_APITOKEN_QSPARAM in cleaned_data.get('token_value')):
            cleaned_data['token_value'] = '%s %s' % (cleaned_data.get('token_key'), cleaned_data.get('token_value'))
            cleaned_data['token_key'] = API_AUTHORIZATION_HEADER

        # Parse authentication data
        cleaned_data = self.clean_authdata(cleaned_data)
        logger.debug('Cleaned authentication data: user=%s\n%s' % (getattr(self, 'user', None), cleaned_data))
        return cleaned_data


class DataServiceAuthorizationForm(IntegrationAuthorizationForm):
    ''' Form class which can be used to approve or deny authentication/authorization
        requests from Data Services that have been registered with Sonador and interact
        with the data services API.
    '''
    def __init__(self, *args, **kwargs):
        self.service = kwargs.pop('service', None)
        super().__init__(*args, **kwargs)

        if not self.service:
            raise ValueError('Unable to initialize authorization form: data service not provided')

    def clean(self, *args, **kwargs):
        ''' Ensure that the form user has access to the data service
        '''
        cleaned_data = super().clean(*args, **kwargs)

        # Ensure that the form user has access to the form service
        if not getattr(self, 'user', None):
            raise forms.ValidationError('Unable to retrieve valid user instance for token')
        if getattr(self, 'user', None) and self.user.pk and not self.service.user_has_perm(self.user):
            raise forms.ValidationError('User "%s" does not have permission to access data service "%s"' % (
                    self.user, self.service.pk
                ))

        return cleaned_data