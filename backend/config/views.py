"""Project-level views.

This module intentionally contains only the minimal Phase 1 health endpoint.
Domain/business views live inside the individual apps under ``backend/apps``.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Liveness probe.

    ``GET /api/health/`` -> ``200 {"status": "ok"}``

    Requires an explicit ``AllowAny``: the project-wide DRF default is
    ``IsAuthenticated`` (D18), so without this opt-out the endpoint returns 401.
    A liveness probe must be reachable before anyone holds credentials.
    """
    return Response({"status": "ok"})
