from django.core import signing
from django.http import JsonResponse
from django.views.generic.base import TemplateView
from django.shortcuts import reverse

from guru.views import GuruApiRequestMixin, GuruApiObjectMixin, GuruApiObjectManagementView, GuruApiRestView
from guru.helpers import operation_results, gsetting
from guru.helpers.utils.object import pick
from guru.errors import OperationError

from core.views import SonadorApiObjectMixin, SonadorApiObjectManagementView, SonadorApiRestView, \
	JSONResponseMixin, JSONBaseView, JSONFormApiView

from ..helpers import SESSION_SALT
from ..apisettings import SONADOR_OHIF_CLIENTID, SONADOR_OHIF_SITE, SONADOR_OHIF_APP, SONADOR_CONFIG_SUPPORTED


