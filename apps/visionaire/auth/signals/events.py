import six, logging, traceback

from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_out

from wgtauth.social.models import SocialAuthorizationToken

from .signals import orthanc_resource_authorization_event, data_service_authorization_event, token_authorization_event
from ..models import SocialAuthorizationServer, SocialUserAccount
from ...apisettings import OPENID_AUTH_TOKEN_SESSION_PROVIDER_PARAM, OPENID_AUTH_TOKEN_SESSION_PARAM, \
	OPENID_AUTH_TOKEN_TYPE_SESSION_PARAM, OPENID_AUTH_TOKEN_SCOPE_SESSION_PARAM
from ..views.service import OrthancServiceAuthorizationView

from ..views.service.integrations import UserProfileAuthorizationView, DataServiceAuthorizationView

logger = logging.getLogger(__name__)

from ...kafka import KafkaManager
kafka_manager = KafkaManager(bootstrap_servers='kafka:9092', client_id='django_service_producer')
kafka_manager.create_topic('audit-event-log')


@receiver(user_logged_out)
def revoke_openid_access_token(sender, user=None, request=None, **kwargs):
	'''	Revoke OpenID access credentials on user logout
	'''
	if request:

		authserverid = request.session.get(OPENID_AUTH_TOKEN_SESSION_PROVIDER_PARAM)
		if authserverid:

			# Retrieve authorization server
			try: authserver = SocialAuthorizationServer.objects.get(pk=authserverid)
			except SocialAuthorizationServer.DoesNotExist: authserver = None

			# Retrieve OpenID access token components
			openid_access_token = request.session.get(OPENID_AUTH_TOKEN_SESSION_PARAM)
			openid_token_type = request.session.get(OPENID_AUTH_TOKEN_TYPE_SESSION_PARAM)

			if authserver and openid_access_token and openid_token_type:

				try:
					authtoken = SocialAuthorizationToken(authserver, {
							'access_token': openid_access_token,
							'token_type': openid_token_type,
						})
					authtoken.revoke()

				except Exception as err:
					logger.error('Unable to revoke OpenID token %s from social provider %s due to an error:\n%s\n%s'
						% (openid_access_token, authserver.label_credentials, err, traceback.format_exc()))
					
@receiver(orthanc_resource_authorization_event, sender=OrthancServiceAuthorizationView)
def orthanc_resource_authorization_event_handler(sender, orthanc_id=None, method=None, level=None, \
													dicom_uid=None, uri=None, user=None, granted=None, \
													validity=None, **kwargs):
	'''	Handle Orthanc resource authorization events
	'''
	logger.info('Orthanc Resource Authorization Event: %s' % kwargs)

	kafka_manager.send_audit_event('audit-event-log', {
		'event': 'orthanc_resource_authorization',
		'orthanc_id': orthanc_id,
		'method': method,
		'level': level,
		'dicom_uid': dicom_uid,
		'uri': uri,
		'user': user,
		'granted': granted,
		'validity': validity
	})

@receiver(token_authorization_event, sender=UserProfileAuthorizationView)
def token_authorization_event_handler(sender, orthanc_id=None, method=None, level=None, \
													dicom_uid=None, uri=None, user=None, granted=None, \
													validity=None, **kwargs):
	'''	Handle Orthanc resource authorization events
	'''
	logger.info('token_authorization_event_handler: %s' % kwargs)
	print("token_authorization_event_handler", kwargs)

	kafka_manager.send_audit_event('audit-event-log', {
		'event': 'orthanc_resource_authorization',
		'orthanc_id': orthanc_id,
		'method': method,
		'level': level,
		'dicom_uid': dicom_uid,
		'uri': uri,
		'user': user,
		'granted': granted,
		'validity': validity
	})

@receiver(data_service_authorization_event, sender=DataServiceAuthorizationView)
def data_service_authorization_event_handler(sender, orthanc_id=None, method=None, level=None, \
													dicom_uid=None, uri=None, user=None, granted=None, \
													validity=None, **kwargs):
	'''	Handle Orthanc resource authorization events
	'''
	logger.info('data_service_authorization_event_handler: %s' % kwargs)
	print("data_service_authorization_event_handler", kwargs)

	kafka_manager.send_audit_event('audit-event-log', {
		'event': 'orthanc_resource_authorization',
		'orthanc_id': orthanc_id,
		'method': method,
		'level': level,
		'dicom_uid': dicom_uid,
		'uri': uri,
		'user': user,
		'granted': granted,
		'validity': validity
	})



	