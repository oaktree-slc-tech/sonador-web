from guru.helpers.compatability import guru_page_not_found, guru_permission_denied
from guru.helpers.user import user_displayname
from guru.helpers import str2bool
from guru.helpers.utils.object import pick

from wgtauth.services.views.integrations import UserProfileAuthorizationView as UserProfileAuthorizaionBaseView, \
    DataServiceAuthorizationView as DataServiceAuthorizationBaseView

from ....apisettings import NGINX_AUTH_REQUEST_QUERY_PARAM
from ...models.integrations import DataService
from ...forms.integrations import IntegrationAuthorizationForm, DataServiceAuthorizationForm


class UserProfileAuthorizationView(UserProfileAuthorizaionBaseView):
    ''' API view which can be used to retrieve the profile for a user by introspecting an API token.
        Generally follows the "Token Introspection" endpoint specified by the oAuth2 standard:
        https://www.oauth.com/oauth2-servers/token-introspection-endpoint/
    '''
    formclass = IntegrationAuthorizationForm


class DataServiceAuthorizationView(DataServiceAuthorizationBaseView):
    ''' API view which can be used to process token validation requests from Data Services
        managed by Sonador and return authorized/denied resposnes. The view has been implemented
        so that it is compatible with the NGINX auth_request module.

        Refer to: https://kubernetes.github.io/ingress-nginx/examples/auth/oauth-external-auth/
    '''
    formclass = DataServiceAuthorizationForm
    dataservice_class = DataService
    