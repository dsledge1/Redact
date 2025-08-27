"""WSGI config for Ultimate PDF project."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ultimate_pdf.settings')

application = get_wsgi_application()