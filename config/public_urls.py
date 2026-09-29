from django.contrib import admin
from django.urls import include, path

from config import health

urlpatterns = [
    path("health/", health.health, name="health"),
    path("readiness/", health.readiness, name="readiness"),
    path("admin/", admin.site.urls),
    path("", include("apps.configuration.urls")),
]
