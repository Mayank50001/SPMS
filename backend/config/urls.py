"""Root URL configuration.

Routes the health probe, the Django admin and the accounts API. Future domain
APIs (``/api/parking-lots/``, ...) are added incrementally, each through its own
``apps/<domain>/urls.py`` module.
"""

from django.contrib import admin
from django.urls import include, path

from .views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.parking.urls")),
    path("api/", include("apps.bookings.urls")),
]

# Placeholder for future app API routing (do NOT enable yet):
# urlpatterns += [path("api/", include("apps.<domain>.urls"))]
