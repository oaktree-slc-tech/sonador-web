from django import forms

from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import Group

from guru.forms import create_modelform_class
from core.forms import SonadorBaseForm


GroupForm = create_modelform_class(Group, base_formclass=SonadorBaseForm)