from ..auth.models import DataService
from ..auth.forms.integrations import DataServiceForm

from .base import SonadorApiRestView


class DataServiceApiRestView(SonadorApiRestView):
    ''' API REST view for Data Services registered with Sonador.
    '''
    model = DataService
    modelform = DataServiceForm

    def getModelJsonData(self, instance, request, vargs=None, vkwargs=None):
        '''	Convert model instance to JSON (dictionary). For GET requests, add
            details about the groups to which the model instance has access.
        '''
        jdata = super(DataServiceApiRestView, self).getModelJsonData(instance, request, vargs=vargs, vkwargs=vkwargs)
        if request.method == 'GET' and instance:

            # Add group details to the object data
            groups = instance.groups.all()
            if groups: jdata['groups'] = [{'id': g.id, 'name': g.name } for g in groups]
        
        return jdata
