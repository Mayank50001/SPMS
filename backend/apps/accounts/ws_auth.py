"""WebSocket authentication (D72, D15/§24).

REST authenticates with a Bearer header (D1). A browser's WebSocket handshake
cannot set headers, so the JWT access token is passed as a query parameter
(``?token=<access>``). This middleware validates it and puts ``scope["user"]``
in place -- the same server-side check the REST API does. A bad or absent token
leaves an ``AnonymousUser``; the consumer decides whether that is acceptable
(for the board it is not).
"""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import close_old_connections


@database_sync_to_async
def _user_for_token(raw_token):
    """Resolve a JWT access token to an active user, or ``None``."""
    if not raw_token:
        return None
    from rest_framework_simplejwt.exceptions import TokenError
    from rest_framework_simplejwt.tokens import AccessToken

    try:
        token = AccessToken(raw_token)
    except TokenError:
        return None
    user_id = token.get("user_id")
    if user_id is None:
        return None
    return get_user_model().objects.filter(pk=user_id, is_active=True).first()


class JwtAuthMiddleware(BaseMiddleware):
    """Authenticate the WebSocket handshake from ``?token=<access>``."""

    async def __call__(self, scope, receive, send):
        close_old_connections()
        query = parse_qs(scope.get("query_string", b"").decode())
        values = query.get("token")
        raw_token = values[0] if values else None
        scope["user"] = await _user_for_token(raw_token) or AnonymousUser()
        return await super().__call__(scope, receive, send)


def JwtAuthMiddlewareStack(inner):
    """JWT auth wrapper for the WebSocket URL router."""
    return JwtAuthMiddleware(inner)