from django.urls import path

from apps.identity.access import management_required

from . import views

app_name = "billing"

urlpatterns = [
    path("", management_required(views.billing_dashboard), name="dashboard"),
    path("facturas/crear/", management_required(views.invoice_create), name="invoice_create"),
    path(
        "facturas/<uuid:pk>/enviar/",
        management_required(views.invoice_submit),
        name="invoice_submit",
    ),
    path("guias/crear/", management_required(views.guide_create), name="guide_create"),
]
