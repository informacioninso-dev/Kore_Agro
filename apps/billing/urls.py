from django.urls import path

from apps.configuration.access import capability_required
from apps.identity.access import management_required

from . import views

app_name = "billing"


def documents_required(view):
    return management_required(capability_required("documents")(view))


urlpatterns = [
    path("", documents_required(views.billing_dashboard), name="dashboard"),
    path("facturas/crear/", documents_required(views.invoice_create), name="invoice_create"),
    path(
        "facturas/<uuid:pk>/enviar/",
        documents_required(views.invoice_submit),
        name="invoice_submit",
    ),
    path("guias/crear/", documents_required(views.guide_create), name="guide_create"),
]
