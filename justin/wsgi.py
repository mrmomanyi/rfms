"""WSGI config for the RFMS project."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'justin.settings')
application = get_wsgi_application()
