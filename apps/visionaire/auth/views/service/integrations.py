from guru.helpers.compatability import guru_page_not_found, guru_permission_denied
from guru.helpers.user import user_displayname
from guru.helpers import str2bool
from guru.helpers.utils.object import pick

from ....apisettings import SONADOR_USERNAME, NGINX_AUTH_REQUEST_QUERY_PARAM
''' API views which provide endpoints for system 
'''
from ...models.integrations import DataService
from ...forms.integrations import IntegrationAuthorizationForm, DataServiceAuthorizationForm

from .base import SonadorServiceAuthorizationBaseView


class UserProfileAuthorizationView(SonadorServiceAuthorizationBaseView):
    ''' API view which can be used to retrieve the profile for a user by introspecting an API token.
        Generally follows the "Token Introspection" endpoint specified by the oAuth2 standard:
        https://www.oauth.com/oauth2-servers/token-introspection-endpoint/
    '''
    formclass = IntegrationAuthorizationForm
    include_groups = False

    def createProfileResponse(self, *args, **kwargs):
        ''' Create response structure
        '''
        return { }

    def getUserProfileJson(self, user, response):
        ''' Retrieve the JSON data for the profile response
        '''
        response['user'] = pick(user, ('id', 'username', 'first_name', 'last_name', 'is_staff', 'is_superuser'))
        response['label_user'] = user_displayname(user)

        if self.include_groups:
            response['user']['groups'] = [self.getGroupJson(g) for g in user.groups.all()]

        return response

    def getGroupJson(self, group):
        ''' Retrieve JSON attributes for the provided group
        '''
        return pick(group, ('id', 'name'))

    def get_data(self, *args, **kwargs):
        ''' Retrieve data for the user profile
        '''
        adata = super().get_data(*args, **kwargs)

        # Authorize oAuth 2.0 token validation requests
        if getattr(self, 'form', None) and self.form.is_valid() and getattr(self.form, 'user', None) \
            and self.user_has_perm(self.form.user):
            adata.update(self.createProfileResponse(*args, **kwargs))

            if not isinstance(self.form.user, str) and self.form.user.pk:
                adata = self.getUserProfileJson(self.form.user, adata)

        return adata

    def user_has_perm(self, user):
        ''' Assess whether the user specified by the token provided to the form has access needed for the resource which 
            the profile is associated with.

            @returns Returns True if the profile should be provided, False otherwise.
        '''
        return True


class DataServiceAuthorizationView(UserProfileAuthorizationView):
    ''' API view which can be used to process token validation requests from Data Services
        managed by Sonador and return authorized/denied resposnes. The view has been implemented
        so that it is compatible with the NGINX auth_request module.

        Refer to: https://kubernetes.github.io/ingress-nginx/examples/auth/oauth-external-auth/
    '''
    formclass = DataServiceAuthorizationForm
    dataservice_class = DataService
    dataservice_request_param = 'objectid'

    nginx_auth_request_query_parameter_name = NGINX_AUTH_REQUEST_QUERY_PARAM

    def getDataService(self, *args, **kwargs):
        ''' Retrieve the data service associated with the request. After being retrieved from
            the database, subsequent calls retrieve a cahced copy of the data.
        '''
        kwargs = kwargs or self.kwargs

        # Retrieve data servicew
        dservice = kwargs.get('service')
        if dservice is None:
            dservice = self.dataservice_class.objects.get(pk=kwargs.get(self.dataservice_request_param))
            kwargs['service'] = dservice
        
        return dservice

    def get_form_kwargs(self, *args, **kwargs):
        form_kwargs = super(DataServiceAuthorizationView, self).get_form_kwargs(*args, **kwargs)
        form_kwargs['service'] = self.getDataService(*args, **kwargs)
        return form_kwargs

    def user_has_perm(self, *args, **kwargs):
        ''' Ensure that the user has access to the data service
        '''
        return self.form.service.user_has_perm(self.form.user)

    def createProfileResponse(self, *args, **kwargs):
        '''Add authorization and validity parameters to the response
        ''' 
        adata = {
            'granted': self.form.is_valid() and self.user_has_perm(self.form.user),
            'service': self.getDataService(*args, **kwargs).pk,
        }

        # Add validity
        if getattr(self.form, 'expires_in', None):
            adata['validity'] = self.form.expires_in
        else: adata['validity'] = 0

        return adata

    def get_data(self, *args, **kwargs):
        ''' Process the authorization request.
        '''
        # Retrieve authorization data from keyword arguments
        adata = super().get_data(*args, **kwargs)

        # Deny requests from unknown users
        if not adata.get('granted'):
            adata.update({ 'granted': False })

        # Cache auth data
        setattr(self.form, 'service_authdata', adata)
        return adata

    def post(self, request, *args, **kwargs):
        ''' Process authorization requests from Data Services
        '''
        # Retrieve the data service and cache
        try: service = self.getDataService(*args, **kwargs)
        except self.dataservice_class.DoesNotExist as err:
            return guru_page_not_found(self.request, err)

        # Set response code based on the query parameters: for NGINX authentication requests
        # nginx-auth=true, return a 403 status code.
        aresponse = super(DataServiceAuthorizationView, self).post(request, *args, **kwargs)
        if hasattr(self.form, 'service_authdata') and not self.form.service_authdata.get('granted') \
            and str2bool(request.GET.get(self.nginx_auth_request_query_parameter_name)):
            aresponse.status_code = 403

        return aresponse
