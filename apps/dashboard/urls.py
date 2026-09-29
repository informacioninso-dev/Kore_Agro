from django.urls import path

from apps.configuration.access import capability_required
from apps.identity.access import management_required

from . import views

app_name = "dashboard"


def management_capability(*codes: str, match_any: bool = False):
    def decorator(view):
        return management_required(capability_required(*codes, match_any=match_any)(view))

    return decorator


urlpatterns = [
    path("", management_required(views.home), name="home"),
    path("pnl/", management_capability("finance")(views.pnl_fragment), name="pnl_fragment"),
    path(
        "actions/",
        management_capability("reproduction", "health", match_any=True)(views.action_list_fragment),
        name="action_list_fragment",
    ),
    path("informacion/", management_required(views.information_center), name="information_center"),
    path(
        "finanzas/",
        management_capability("finance")(views.finance_dashboard),
        name="finance_dashboard",
    ),
    path(
        "crecimiento/",
        management_capability("growth")(views.growth_dashboard),
        name="growth_dashboard",
    ),
    path(
        "crecimiento/pesaje/",
        management_capability("growth")(views.growth_record_weight),
        name="growth_record_weight",
    ),
    path(
        "animales/<uuid:pk>/historial/",
        management_capability("herd", "growth", match_any=True)(views.animal_timeline),
        name="animal_timeline",
    ),
    path(
        "finanzas/fragmento/",
        management_capability("finance")(views.finance_fragment),
        name="finance_fragment",
    ),
    path(
        "finanzas/cierre/",
        management_capability("finance")(views.finance_close_period),
        name="finance_close_period",
    ),
    path(
        "finanzas/gasto/",
        management_capability("finance")(views.finance_record_expense),
        name="finance_record_expense",
    ),
    path(
        "finanzas/venta-animal/",
        management_capability("finance")(views.finance_record_animal_sale),
        name="finance_record_animal_sale",
    ),
    path(
        "datos/",
        management_capability("herd", "inventory", match_any=True)(views.master_data),
        name="master_data",
    ),
    path(
        "datos/haciendas/crear/",
        management_capability("herd", "inventory", match_any=True)(views.farm_create),
        name="farm_create",
    ),
    path(
        "datos/haciendas/<uuid:pk>/editar/",
        management_capability("herd", "inventory", match_any=True)(views.farm_edit),
        name="farm_edit",
    ),
    path(
        "datos/haciendas/<uuid:pk>/actualizar/",
        management_capability("herd", "inventory", match_any=True)(views.farm_update),
        name="farm_update",
    ),
    path(
        "datos/haciendas/<uuid:pk>/desactivar/",
        management_capability("herd", "inventory", match_any=True)(views.farm_deactivate),
        name="farm_deactivate",
    ),
    path(
        "datos/lotes/crear/", management_capability("herd")(views.group_create), name="group_create"
    ),
    path(
        "datos/lotes/<uuid:pk>/editar/",
        management_capability("herd")(views.group_edit),
        name="group_edit",
    ),
    path(
        "datos/lotes/<uuid:pk>/actualizar/",
        management_capability("herd")(views.group_update),
        name="group_update",
    ),
    path(
        "datos/lotes/<uuid:pk>/desactivar/",
        management_capability("herd")(views.group_deactivate),
        name="group_deactivate",
    ),
    path(
        "datos/animales/crear/",
        management_capability("herd")(views.animal_create),
        name="animal_create",
    ),
    path(
        "datos/animales/<uuid:pk>/editar/",
        management_capability("herd")(views.animal_edit),
        name="animal_edit",
    ),
    path(
        "datos/animales/<uuid:pk>/actualizar/",
        management_capability("herd")(views.animal_update),
        name="animal_update",
    ),
    path(
        "datos/animales/<uuid:pk>/desactivar/",
        management_capability("herd")(views.animal_deactivate),
        name="animal_deactivate",
    ),
    path(
        "datos/insumos/crear/",
        management_capability("inventory")(views.input_create),
        name="input_create",
    ),
    path(
        "datos/insumos/<uuid:pk>/editar/",
        management_capability("inventory")(views.input_edit),
        name="input_edit",
    ),
    path(
        "datos/insumos/<uuid:pk>/actualizar/",
        management_capability("inventory")(views.input_update),
        name="input_update",
    ),
    path(
        "datos/insumos/<uuid:pk>/desactivar/",
        management_capability("inventory")(views.input_deactivate),
        name="input_deactivate",
    ),
    path(
        "datos/stock/crear/",
        management_capability("inventory")(views.stock_lot_create),
        name="stock_lot_create",
    ),
    path(
        "datos/stock/<uuid:pk>/editar/",
        management_capability("inventory")(views.stock_lot_edit),
        name="stock_lot_edit",
    ),
    path(
        "datos/stock/<uuid:pk>/actualizar/",
        management_capability("inventory")(views.stock_lot_update),
        name="stock_lot_update",
    ),
    path(
        "datos/stock/<uuid:pk>/desactivar/",
        management_capability("inventory")(views.stock_lot_deactivate),
        name="stock_lot_deactivate",
    ),
    path(
        "datos/stock/recepcion/",
        management_capability("inventory")(views.inventory_receive),
        name="inventory_receive",
    ),
    path(
        "datos/stock/ajuste/",
        management_capability("inventory")(views.inventory_adjust),
        name="inventory_adjust",
    ),
]
