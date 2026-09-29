from django.urls import path

from apps.configuration.access import capability_required
from apps.identity.access import management_required

from . import views

app_name = "workforce"


def workforce_required(view):
    return management_required(capability_required("workforce")(view))


urlpatterns = [
    path("", workforce_required(views.dashboard), name="dashboard"),
    path("personal/crear/", workforce_required(views.worker_create), name="worker_create"),
    path(
        "personal/<uuid:pk>/editar/",
        workforce_required(views.worker_edit),
        name="worker_edit",
    ),
    path(
        "personal/<uuid:pk>/actualizar/",
        workforce_required(views.worker_update),
        name="worker_update",
    ),
    path(
        "personal/<uuid:pk>/desactivar/",
        workforce_required(views.worker_deactivate),
        name="worker_deactivate",
    ),
    path("tareas/crear/", workforce_required(views.task_create), name="task_create"),
    path(
        "tareas/<uuid:pk>/editar/",
        workforce_required(views.task_edit),
        name="task_edit",
    ),
    path(
        "tareas/<uuid:pk>/actualizar/",
        workforce_required(views.task_update),
        name="task_update",
    ),
    path("tareas/accion/", workforce_required(views.task_action), name="task_action"),
    path(
        "tareas/<uuid:pk>/cancelar/",
        workforce_required(views.task_cancel),
        name="task_cancel",
    ),
]
