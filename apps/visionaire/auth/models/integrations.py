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
    
    @property
    def json(self):
        odata = { 'service_id': self.pk }
        odata.update(pick(self, ('description', 'active', 'acl_allow_staff')))
        return odata
