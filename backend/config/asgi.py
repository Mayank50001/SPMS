"""
ASGI config for backend project (D72).

Plain HTTP goes to Django; WebSocket connections (the live occupancy board) go
through Channels. ``get_asgi_application()`` must run *before* the routing
import so the app registry is ready when the consumers load.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_application = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from config.routing import websocket_urlpatterns  # noqa: E402
from apps.accounts.ws_auth import JwtAuthMiddlewareStack  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": JwtAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)