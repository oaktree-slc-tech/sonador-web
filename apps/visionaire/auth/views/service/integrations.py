from guru.helpers.compatability import guru_page_not_found, guru_permission_denied
from guru.helpers.user import user_displayname
from guru.helpers.utils.object import pick

from ...models.integrations import DataService
from ...forms.integrations import DataServiceAuthorizationForm

from .base import SonadorServiceAuthorizationBaseView


class DataServiceAuthorizationView(SonadorServiceAuthorizationBaseView):
    ''' API view which can be used to process token validation requests from Data Services
        managed by Sonador.
    '''
    formclass = DataServiceAuthorizationForm
    dataservice_class = DataService
    dataservice_request_param = 'objectid'

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
    
    def get_data(self, *args, **kwargs):
        ''' Process the authorization request.
        '''
        adata = super(DataServiceAuthorizationView, self).get_data(*args, **kwargs)

        # Authorize token validation requests from oAuth2.0 data services
        if self.form.is_valid() and getattr(self.form, 'user', None):

            # Valid authorization forms resolve to the "Sonador" internal user or to a user
            # account. The internal user is a superadmin authorized to access or modify any
            # service. User accounts require permission to access the resource they have request.
            # Resource requests can be verified by calling the user_has_perm method on the data 
            # service model.
            if self.form.user == 'sonador' \
				or (self.form.user.pk and self.form.service.user_has_perm(self.form.user)):

                # Grant the request and provide details about the user
                adata.update({
                    'granted': True, 'validity': self.form.expires_in,
                    'user': pick(self.form.user, ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser')),
                })
                adata['user']['label_user'] = user_displayname(self.form.user)
        
        # Deny requests from unknown users
        if not adata.get('granted'):
            adata.update({ 'granted': False })
        
        return adata
    
    def post(self, request, *args, **kwargs):
        ''' Process authorization requests from Data Services
        '''
        # Retrieve the data service and cache
        try: service = self.getDataService(*args, **kwargs)
        except self.dataservice_class.DoesNotExist as err:
            return guru_page_not_found(self.request, err)
        
        return super(DataServiceAuthorizationView, self).post(request, *args, **kwargs)
    