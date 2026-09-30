from django.urls import path

from apps.configuration.access import capability_required
from apps.identity.access import management_required

from . import views

app_name = "procurement"


def procurement_required(view):
    return management_required(capability_required("procurement")(view))


urlpatterns = [
    path("", procurement_required(views.dashboard), name="dashboard"),
    path("proveedores/crear/", procurement_required(views.supplier_create), name="supplier_create"),
    path(
        "proveedores/<uuid:pk>/editar/",
        procurement_required(views.supplier_edit),
        name="supplier_edit",
    ),
    path(
        "proveedores/<uuid:pk>/actualizar/",
        procurement_required(views.supplier_update),
        name="supplier_update",
    ),
    path(
        "proveedores/<uuid:pk>/desactivar/",
        procurement_required(views.supplier_deactivate),
        name="supplier_deactivate",
    ),
    path("ordenes/crear/", procurement_required(views.order_create), name="order_create"),
    path("ordenes/lineas/crear/", procurement_required(views.line_create), name="line_create"),
    path("ordenes/accion/", procurement_required(views.order_action), name="order_action"),
    path("recepciones/crear/", procurement_required(views.receipt_create), name="receipt_create"),
]
