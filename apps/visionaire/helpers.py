from guru.helpers import gsetting
from wgtauth.services.apisettings import ACCESS_TOKEN_MAX_AGE, \
	API_REFERRER_REFERER_HEADER, API_AUTHORIZATION_HEADER, API_ACCESS_APITOKEN_QSPARAM, \
	API_ACCESS_TOKEN_QSPARAM, API_ACCESS_SERVER_TOKEN


SESSION_SALT = gsetting('SESSION_SALT', 'sonador-session-salt')
