from django.urls import path

from apps.configuration.access import capability_required
from apps.identity.access import management_required, tenant_permission_required

from . import views

app_name = "audit"


urlpatterns = [
    path(
        "",
        management_required(
            capability_required("audit")(
                tenant_permission_required("audit.view_auditevent")(views.dashboard)
            )
        ),
        name="dashboard",
    )
]
