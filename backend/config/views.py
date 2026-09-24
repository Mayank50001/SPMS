"""Project-level views.

This module intentionally contains only the minimal Phase 1 health endpoint.
Domain/business views live inside the individual apps under ``backend/apps``.
"""

from django.http import JsonResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def health(request):
    """Liveness probe.

    ``GET /api/health/`` -> ``200 {"status": "ok"}``

    Used by the frontend dev proxy and by deployment/orchestration checks to
    confirm the Django application is serving requests.
    """
    return Response({"status": "ok"})


def health_plain(request):
    """Dependency-free health check using Django's own JSON response.

    Kept as a fallback that does not touch Django REST Framework, so the
    endpoint remains verifiable even before DRF is exercised.
    """
    return JsonResponse({"status": "ok"})
