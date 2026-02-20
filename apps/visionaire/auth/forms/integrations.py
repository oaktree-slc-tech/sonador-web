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
from wgtauth.services.forms import DataServiceBaseForm
from wgtauth.services.forms.integrations import IntegrationAuthorizationForm as IntegrationAuthorizationBaseForm, \
    DataServiceAuthorizationForm as DataserviceAuthorizationBaseForm

from ...helpers import API_AUTHORIZATION_HEADER, SESSION_SALT, ACCESS_TOKEN_MAX_AGE, \
	API_ACCESS_SERVER_TOKEN, API_ACCESS_TOKEN_QSPARAM, API_ACCESS_APITOKEN_QSPARAM, \
	API_REFERRER_REFERER_HEADER

from .base import ServiceAuthorizationRequest, SonadorServiceAuthorizationBaseForm

logger = logging.getLogger(__name__)


from ..models import DataService


class DataServiceForm(DataServiceBaseForm):
    ''' Form class for creating and updating Sonador data services
    '''
    class Meta:
        model = DataService
        fields = '__all__'
        exclude = ('token',)


class IntegrationAuthorizationForm(IntegrationAuthorizationBaseForm):
    ''' Form class which can be used to approve or deny authentication/authorization requests
        from systems which integrate with Sonador
    '''
    credential_providers = SonadorServiceAuthorizationBaseForm.credential_providers
    cache_credential_providers = SonadorServiceAuthorizationBaseForm.cache_credential_providers


class DataServiceAuthorizationForm(DataserviceAuthorizationBaseForm):
    ''' Form class which can be used to approve or deny authentication/authorization
        requests from Data Services that have been registered with Sonador and interact
        with the data services API.
    '''
    credential_providers = SonadorServiceAuthorizationBaseForm.credential_providers
    cache_credential_providers = SonadorServiceAuthorizationBaseForm.cache_credential_providers