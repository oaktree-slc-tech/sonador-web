import os
from django.core.asgi import get_asgi_application

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


# Django configuration
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sonador.settings')
django_app = get_asgi_application()


# FastAPI configuration for serving static files
from guru.helpers import gsetting
STATIC_ROOT = gsetting('STATIC_ROOT')
STATIC_URL = gsetting('STATIC_URL')

# Static files
fastapi_app = FastAPI()
fastapi_app.mount(STATIC_URL, StaticFiles(directory=STATIC_ROOT), name='static')

# Sonador web application
fastapi_app.mount('/', django_app)

application = fastapi_app