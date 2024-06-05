import django.dispatch


# Custom Registration and Authentication Signals
socialuser_first_login = django.dispatch.Signal(['request', 'social_profile', 'registration'])
orthanc_resource_authorization_event = django.dispatch.Signal(['orthanc_id', 'method', 'level', 'dicom_uid', 'uri', 'user', 'granted', 'validity'])
data_service_authorization_event = django.dispatch.Signal(['orthanc_id', 'method', 'level', 'dicom_uid', 'uri', 'user', 'granted', 'validity'])
token_authorization_event = django.dispatch.Signal(['orthanc_id', 'method', 'level', 'dicom_uid', 'uri', 'user', 'granted', 'validity'])