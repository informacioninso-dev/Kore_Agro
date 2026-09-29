from django.contrib import admin
from django.urls import include, path

from apps.sync.api import api as sync_api
from config import health

urlpatterns = [
    path("health/", health.health, name="health"),
    path("readiness/", health.readiness, name="readiness"),
    path("", include("apps.identity.urls")),
    path("admin/", admin.site.urls),
    path("cumplimiento/", include("apps.billing.urls")),
    path("pastoreo/", include("apps.grazing.urls")),
    path("trabajo/", include("apps.workforce.urls")),
    path("", include("apps.dashboard.urls")),
    path("field/", include("apps.sync.field_urls")),
    path("api/", sync_api.urls),
]

