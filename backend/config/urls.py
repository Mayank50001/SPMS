"""Root URL configuration.

Only the health endpoint and the Django admin are routed at this phase.
Application URLs (``/api/accounts/``, ``/api/parking-lots/``, ...) will be
added incrementally, each through its own ``apps/<domain>/urls.py`` module.
"""

from django.contrib import admin
from django.urls import include, path

from .views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/", include("apps.accounts.urls"))
]

# Placeholder for future app API routing (do NOT enable yet):
# urlpatterns += [path("api/", include("apps.<domain>.urls"))]
