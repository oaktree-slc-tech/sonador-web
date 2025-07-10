from django.db import models
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField


class UserPref(models.Model):
    ''' Allows for the OHIF frontend application to persist user settings and preferences
    '''
    uid = models.BigAutoField(primary_key=True, unique=True, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    viewer = models.JSONField(null=True, blank=True)
    studylist = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"Entry {self.uid} : {self.user}"