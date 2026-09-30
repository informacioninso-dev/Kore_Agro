from django.urls import path

from apps.configuration.access import capability_required
from apps.identity.access import management_required, tenant_permission_required

from . import views

app_name = "procurement"


def procurement_required(view):
    return management_required(capability_required("procurement")(view))


def procurement_permission(permission_name):
    def decorator(view):
        return procurement_required(tenant_permission_required(permission_name)(view))

    return decorator


urlpatterns = [
    path(
        "",
        procurement_permission("procurement.view_purchaseorder")(views.dashboard),
        name="dashboard",
    ),
    path(
        "proveedores/crear/",
        procurement_permission("parties.add_counterparty")(views.supplier_create),
        name="supplier_create",
    ),
    path(
        "proveedores/<uuid:pk>/editar/",
        procurement_permission("parties.change_counterparty")(views.supplier_edit),
        name="supplier_edit",
    ),
    path(
        "proveedores/<uuid:pk>/actualizar/",
        procurement_permission("parties.change_counterparty")(views.supplier_update),
        name="supplier_update",
    ),
    path(
        "proveedores/<uuid:pk>/desactivar/",
        procurement_permission("parties.change_counterparty")(views.supplier_deactivate),
        name="supplier_deactivate",
    ),
    path(
        "ordenes/crear/",
        procurement_permission("procurement.add_purchaseorder")(views.order_create),
        name="order_create",
    ),
    path(
        "ordenes/lineas/crear/",
        procurement_permission("procurement.change_purchaseorder")(views.line_create),
        name="line_create",
    ),
    path("ordenes/accion/", procurement_required(views.order_action), name="order_action"),
    path(
        "recepciones/crear/",
        procurement_permission("procurement.receive_purchaseorder")(views.receipt_create),
        name="receipt_create",
    ),
    path(
        "facturas/crear/",
        procurement_permission("procurement.manage_purchaseinvoice")(views.invoice_create),
        name="invoice_create",
    ),
    path(
        "pagos/crear/",
        procurement_permission("procurement.pay_purchaseinvoice")(views.payment_create),
        name="payment_create",
    ),
    path(
        "devoluciones/crear/",
        procurement_permission("procurement.return_purchase")(views.return_create),
        name="return_create",
    ),
]
