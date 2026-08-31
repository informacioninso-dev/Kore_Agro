from django.urls import path

from apps.identity.access import field_access_required

from . import views

app_name = "field"

urlpatterns = [
    path("", field_access_required(views.field_app), name="app"),
    path("sw.js", field_access_required(views.service_worker), name="service_worker"),
    path("manifest.webmanifest", field_access_required(views.webmanifest), name="manifest"),
]

