import logging, json, fnmatch, posixpath, copy
from django.db import models

from django.urls import reverse
from django.contrib import auth

from django.db import models
from django.contrib.auth.models import User, Group

from microservices.control import server_controlurl, \
	server_controloperation_post, server_controloperation_put, server_controloperation_delete
from microservices.control.jsonapi import server_controloperation_get

import guru.apisettings as gapicodes
from guru.models import GuruTokenModel
from guru.helpers import site_fullurl
from guru.helpers.compatability import guru_is_safe_url
from guru.helpers.utils.object import pick, omit

from wgtauth.apisettings import OAUTH_TOKEN_RESPONSE_TYPE, OAUTH_CODE_RESPONSE_TYPE, \
	OAUTH_CODE_RESPONSE_TYPE

from wgtauth.social.models import SocialAuthorizationBaseServer, OPENID_RESPONSE_TYPE_CODE

from orthancapi import apisettings as orthanc_api
from orthancapi.auth.acl import ServerAuthorization as OrthancServerAuthorization, \
	ResourceAuthorization as OrthancResourceAuthorization
from orthancapi.auth.validation import SonadorGroup as OrthancSonadorGroup, \
	SonadorUser as OrthancSonadorUser, SonadorResourceAuthorizationRequest

from ...apisettings import SONADOR_PERMS, ORTHANC_DICOMWEB_STUDIES, ORTHANC_DICOMWEB_SERIES, ORTHANC_WADO, \
	ORTHANC_CACHE_PATIENT, ORTHANC_CACHE_STUDY, ORTHANC_CACHE_SERIES, \
	ORTHANC_INSTANCES, ORTHANC_TOOLS_FIND, ORTHANC_SYSTEM, ORTHANC_IMAGING_RESOURCES, ORTHANC_QUERY_RESOURCES, ORTHANC_COMMENTS, \
	WILDCARD, ORTHANC_RESOURCE_URL, ORTHANC_RESOURCE_URL_PATIENT, ORTHANC_RESOURCE_URL_STUDY, ORTHANC_RESOURCE_URL_SERIES

from ..helpers import parse_resource_policy
from .integrations import DataService
from .user import SonadorProxyUser, SonadorProxyGroup
from .auth import SocialAuthorizationServer, SocialUserAccount, PacsImagingServerUserAuthorization, \
	PacsImagingServerGroupAuthorization
