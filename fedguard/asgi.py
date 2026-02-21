"""
FedGuard ASGI Configuration
-----------------------------
Routes:
  /api/*  → FastAPI (async ML endpoints)
  /*      → Django (templates, dashboard, admin, static files)

This dual-mount design gives us Django's ORM + admin and FastAPI's
async performance in a single process on a single port.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fedguard.settings')
django.setup()

from django.core.asgi import get_asgi_application
from main.api.app import api_app

django_app = get_asgi_application()


async def application(scope, receive, send):
    if scope['type'] == 'http':
        path = scope.get('path', '')
        if path.startswith('/api/'):
            # FastAPI handles all /api/* routes
            await api_app(scope, receive, send)
            return
    # Django handles everything else (templates, admin, static)
    await django_app(scope, receive, send)
