from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("pnl/", views.pnl_fragment, name="pnl_fragment"),
    path("actions/", views.action_list_fragment, name="action_list_fragment"),
    path("finanzas/", views.finance_dashboard, name="finance_dashboard"),
    path("finanzas/fragmento/", views.finance_fragment, name="finance_fragment"),
    path("finanzas/cierre/", views.finance_close_period, name="finance_close_period"),
    path("finanzas/gasto/", views.finance_record_expense, name="finance_record_expense"),
    path(
        "finanzas/venta-animal/",
        views.finance_record_animal_sale,
        name="finance_record_animal_sale",
    ),
    path("datos/", views.master_data, name="master_data"),
    path("datos/haciendas/crear/", views.farm_create, name="farm_create"),
    path("datos/haciendas/<uuid:pk>/editar/", views.farm_edit, name="farm_edit"),
    path("datos/haciendas/<uuid:pk>/actualizar/", views.farm_update, name="farm_update"),
    path("datos/haciendas/<uuid:pk>/desactivar/", views.farm_deactivate, name="farm_deactivate"),
    path("datos/lotes/crear/", views.group_create, name="group_create"),
    path("datos/lotes/<uuid:pk>/editar/", views.group_edit, name="group_edit"),
    path("datos/lotes/<uuid:pk>/actualizar/", views.group_update, name="group_update"),
    path("datos/lotes/<uuid:pk>/desactivar/", views.group_deactivate, name="group_deactivate"),
    path("datos/animales/crear/", views.animal_create, name="animal_create"),
    path("datos/animales/<uuid:pk>/editar/", views.animal_edit, name="animal_edit"),
    path("datos/animales/<uuid:pk>/actualizar/", views.animal_update, name="animal_update"),
    path("datos/animales/<uuid:pk>/desactivar/", views.animal_deactivate, name="animal_deactivate"),
    path("datos/insumos/crear/", views.input_create, name="input_create"),
    path("datos/insumos/<uuid:pk>/editar/", views.input_edit, name="input_edit"),
    path("datos/insumos/<uuid:pk>/actualizar/", views.input_update, name="input_update"),
    path("datos/insumos/<uuid:pk>/desactivar/", views.input_deactivate, name="input_deactivate"),
    path("datos/stock/crear/", views.stock_lot_create, name="stock_lot_create"),
    path("datos/stock/<uuid:pk>/editar/", views.stock_lot_edit, name="stock_lot_edit"),
    path("datos/stock/<uuid:pk>/actualizar/", views.stock_lot_update, name="stock_lot_update"),
    path(
        "datos/stock/<uuid:pk>/desactivar/",
        views.stock_lot_deactivate,
        name="stock_lot_deactivate",
    ),
    path("datos/stock/recepcion/", views.inventory_receive, name="inventory_receive"),
    path("datos/stock/ajuste/", views.inventory_adjust, name="inventory_adjust"),
]
