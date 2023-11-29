import django.dispatch


# Custom Registration and Authentication Signals
socialuser_first_login = django.dispatch.Signal(['request', 'social_profile', 'registration'])
