from django.urls import path

from apps.configuration.access import capability_required
from apps.identity.access import field_access_required

from . import views

app_name = "field"


def field_module_required(view):
    return field_access_required(capability_required("field_offline")(view))


urlpatterns = [
    path("", field_module_required(views.field_app), name="app"),
    path("sw.js", field_module_required(views.service_worker), name="service_worker"),
    path("manifest.webmanifest", field_module_required(views.webmanifest), name="manifest"),
]
