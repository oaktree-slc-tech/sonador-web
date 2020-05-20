from guru.helpers import gsetting


SESSION_SALT = gsetting('SESSION_SALT', 'sonador-session-salt')
ACCESS_TOKEN_MAX_AGE = int(gsetting('ACCESS_TOKEN_MAX_AGE', 60*60*3))

API_REFERRER_REFERER_HEADER = 'Referer'

API_ACCESS_APITOKEN_QSPARAM = 'api-token'
API_ACCESS_TOKEN_QSPARAM = 'token'