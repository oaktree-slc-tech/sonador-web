from django.conf.urls import url
from .views import OpenIDLoginRedirectView, OpenIDLoginCallbackView


urlpatterns_openid_auth = [

	# Authenticate via Social Media
	url(r'^(?P<serverid>\w+)/?$', OpenIDLoginRedirectView.as_view(), name='openid-login'),
	url(r'^(?P<serverid>\w+)/callback/?$', OpenIDLoginCallbackView.as_view(), name='openid-login-callback'),
]
