from django.urls import path

from apps.configuration.access import capability_required
from apps.identity.access import management_required

from . import views

app_name = "grazing"


def grazing_required(view):
    return management_required(capability_required("grazing")(view))


urlpatterns = [
    path("", grazing_required(views.dashboard), name="dashboard"),
    path("potreros/crear/", grazing_required(views.paddock_create), name="paddock_create"),
    path(
        "potreros/<uuid:pk>/editar/",
        grazing_required(views.paddock_edit),
        name="paddock_edit",
    ),
    path(
        "potreros/<uuid:pk>/actualizar/",
        grazing_required(views.paddock_update),
        name="paddock_update",
    ),
    path(
        "potreros/<uuid:pk>/desactivar/",
        grazing_required(views.paddock_deactivate),
        name="paddock_deactivate",
    ),
    path("rotaciones/iniciar/", grazing_required(views.rotation_start), name="rotation_start"),
    path(
        "rotaciones/<uuid:pk>/cerrar/",
        grazing_required(views.rotation_finish),
        name="rotation_finish",
    ),
]
