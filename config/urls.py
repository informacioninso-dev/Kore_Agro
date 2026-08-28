from django.contrib import admin
from django.urls import include, path

from apps.sync.api import api as sync_api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.dashboard.urls")),
    path("field/", include("apps.sync.field_urls")),
    path("api/", sync_api.urls),
]

