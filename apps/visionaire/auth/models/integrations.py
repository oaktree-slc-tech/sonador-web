from django.db import models
from django.contrib.auth.models import Group

from guru.models import GuruTokenModel
from guru.helpers.utils.object import pick, omit


class DataService(GuruTokenModel):
    ''' Data service associated with Sonador. Data services are able to utilize
        Sonador access credentials (API tokens, access ID/secret, and session tokens)
        for authentication via oAuth2.0 token introspection.
    '''
    description = models.CharField(max_length=2048)
    active = models.BooleanField(verbose_name='Active', default=True)
    acl_allow_staff = models.BooleanField(verbose_name='Allow Staff', default=True,
        help_text='Allow users with "staff" permissions to access the data service.')

    groups = models.ManyToManyField(Group, help_text='Groups authorized to access the data service via API requests.')

    class Meta:
        ordering = ('description',)

    def __str__(self, *args, **kwargs):
        return '%s: %s' % (self.pk, self.description)

    def user_has_perm(self, user):
        ''' Determine if the provided user has the needed permission to perform the requested action.
            
            @returns bool: True if the user has the permission, False otherwise
        '''
        # Administrative users can access all data services
        if user.is_superuser:
            return True
        
        # Allow staff users to access the service if indicated by the service settings
        if self.acl_allow_staff and user.is_staff:
            return True
        
        # Determine if the user is part of a group that has the requested permissions
        for auth in self.groups.filter(group__user):
            return True
        
        return False
    
    @property
    def json(self):
        odata = { 'service_id': self.pk }
        odata.update(pick(self, ('description', 'active', 'acl_allow_staff')))
        return odata
