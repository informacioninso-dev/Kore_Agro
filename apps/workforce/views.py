from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.herd.models import Farm

from .forms import TaskActionForm, WorkerForm, WorkTaskForm
from .models import Worker, WorkLog, WorkTask
from .services import cancel_task, complete_task, start_task


def _selected_farm(request: HttpRequest) -> Farm | None:
    farm_id = request.POST.get("farm") or request.GET.get("farm")
    if farm_id:
        return Farm.objects.filter(pk=farm_id, is_active=True).first()
    return Farm.objects.filter(is_active=True).order_by("name").first()


def _error_text(exc: ValidationError) -> str:
    return " ".join(exc.messages)


def _workforce_context(
    request: HttpRequest,
    *,
    farm: Farm | None = None,
    overrides: dict | None = None,
) -> dict:
    selected_farm = farm or _selected_farm(request)
    today = timezone.localdate()
    workers = Worker.objects.none()
    open_tasks = WorkTask.objects.none()
    recent_tasks = WorkTask.objects.none()
    work_logs = WorkLog.objects.none()
    month_hours = Decimal("0")
    month_cost = Decimal("0")
    if selected_farm:
        workers = Worker.objects.filter(farm=selected_farm, is_active=True).select_related("user")
        open_tasks = WorkTask.objects.filter(
            farm=selected_farm,
            status__in=(WorkTask.Status.PENDING, WorkTask.Status.IN_PROGRESS),
        ).select_related("assigned_to", "group", "animal", "paddock")
        recent_tasks = WorkTask.objects.filter(
            farm=selected_farm,
            status__in=(WorkTask.Status.COMPLETED, WorkTask.Status.CANCELLED),
        ).select_related("assigned_to")[:12]
        work_logs = WorkLog.objects.filter(task__farm=selected_farm).select_related(
            "task", "worker", "cost_allocation"
        )[:20]
        month_logs = WorkLog.objects.filter(
            task__farm=selected_farm,
            work_date__year=today.year,
            work_date__month=today.month,
        ).aggregate(hours=Sum("hours"), cost=Sum("labor_cost"))
        month_hours = month_logs["hours"] or Decimal("0")
        month_cost = month_logs["cost"] or Decimal("0")

    context = {
        "farms": Farm.objects.filter(is_active=True).order_by("name"),
        "selected_farm": selected_farm,
        "workers": workers,
        "open_tasks": open_tasks,
        "recent_tasks": recent_tasks,
        "work_logs": work_logs,
        "active_workers": workers.count(),
        "pending_count": open_tasks.filter(status=WorkTask.Status.PENDING).count(),
        "in_progress_count": open_tasks.filter(status=WorkTask.Status.IN_PROGRESS).count(),
        "overdue_count": open_tasks.filter(scheduled_for__lt=today).count(),
        "month_hours": month_hours,
        "month_cost": month_cost,
        "worker_form": WorkerForm(farm=selected_farm, initial={"farm": selected_farm}),
        "task_form": WorkTaskForm(farm=selected_farm, initial={"farm": selected_farm}),
        "action_form": TaskActionForm(farm=selected_farm),
        "worker_edit_id": None,
        "task_edit_id": None,
        "workforce_message": "",
        "workforce_error": "",
    }
    if overrides:
        context.update(overrides)
    return context


def dashboard(request: HttpRequest) -> HttpResponse:
    return render(request, "workforce/dashboard.html", _workforce_context(request))


@require_POST
def worker_create(request: HttpRequest) -> HttpResponse:
    farm = _selected_farm(request)
    form = WorkerForm(request.POST, farm=farm)
    if not form.is_valid():
        return _render_error(request, farm, {"worker_form": form}, "Revisa el trabajador.")
    worker = form.save()
    return _render_success(request, worker.farm, f"Trabajador {worker.full_name} creado.")


def worker_edit(request: HttpRequest, pk) -> HttpResponse:
    worker = get_object_or_404(Worker, pk=pk, is_active=True)
    return render(
        request,
        "workforce/dashboard.html",
        _workforce_context(
            request,
            farm=worker.farm,
            overrides={
                "worker_form": WorkerForm(instance=worker, farm=worker.farm),
                "worker_edit_id": worker.id,
            },
        ),
    )


@require_POST
def worker_update(request: HttpRequest, pk) -> HttpResponse:
    worker = get_object_or_404(Worker, pk=pk, is_active=True)
    form = WorkerForm(request.POST, instance=worker, farm=worker.farm)
    if not form.is_valid():
        return _render_error(
            request,
            worker.farm,
            {"worker_form": form, "worker_edit_id": worker.id},
            "Revisa el trabajador.",
        )
    worker = form.save()
    return _render_success(request, worker.farm, f"Trabajador {worker.full_name} actualizado.")


@require_POST
def worker_deactivate(request: HttpRequest, pk) -> HttpResponse:
    worker = get_object_or_404(Worker, pk=pk, is_active=True)
    if worker.tasks.filter(
        status__in=(WorkTask.Status.PENDING, WorkTask.Status.IN_PROGRESS)
    ).exists():
        return _render_error(
            request,
            worker.farm,
            {},
            "Reasigna o cancela las tareas abiertas antes de desactivar al trabajador.",
        )
    worker.ended_on = timezone.localdate()
    worker.soft_delete()
    worker.save(update_fields=["ended_on", "updated_at"])
    return _render_success(request, worker.farm, f"Trabajador {worker.full_name} desactivado.")


@require_POST
def task_create(request: HttpRequest) -> HttpResponse:
    farm = _selected_farm(request)
    form = WorkTaskForm(request.POST, farm=farm)
    if not form.is_valid():
        return _render_error(request, farm, {"task_form": form}, "Revisa la tarea.")
    task = form.save()
    return _render_success(request, task.farm, f"Tarea {task.title} creada.")


def task_edit(request: HttpRequest, pk) -> HttpResponse:
    task = get_object_or_404(
        WorkTask,
        pk=pk,
        status__in=(WorkTask.Status.PENDING, WorkTask.Status.IN_PROGRESS),
    )
    return render(
        request,
        "workforce/dashboard.html",
        _workforce_context(
            request,
            farm=task.farm,
            overrides={
                "task_form": WorkTaskForm(instance=task, farm=task.farm),
                "task_edit_id": task.id,
            },
        ),
    )


@require_POST
def task_update(request: HttpRequest, pk) -> HttpResponse:
    task = get_object_or_404(
        WorkTask,
        pk=pk,
        status__in=(WorkTask.Status.PENDING, WorkTask.Status.IN_PROGRESS),
    )
    form = WorkTaskForm(request.POST, instance=task, farm=task.farm)
    if not form.is_valid():
        return _render_error(
            request,
            task.farm,
            {"task_form": form, "task_edit_id": task.id},
            "Revisa la tarea.",
        )
    task = form.save()
    return _render_success(request, task.farm, f"Tarea {task.title} actualizada.")


@require_POST
def task_action(request: HttpRequest) -> HttpResponse:
    farm = _selected_farm(request)
    form = TaskActionForm(request.POST, farm=farm)
    if not form.is_valid():
        return _render_error(
            request,
            farm,
            {"action_form": form},
            "Revisa la actualizacion de la tarea.",
        )
    data = form.cleaned_data
    try:
        if data["action"] == TaskActionForm.Action.START:
            task = start_task(data["task"], worker=data["worker"])
            message = f"Tarea {task.title} iniciada."
        else:
            log = complete_task(
                data["task"],
                worker=data["worker"],
                hours=data["hours"],
                notes=data["notes"],
            )
            message = f"Tarea {log.task.title} completada; costo laboral $ {log.labor_cost}."
    except ValidationError as exc:
        return _render_error(request, farm, {"action_form": form}, _error_text(exc))
    return _render_success(request, farm, message)


@require_POST
def task_cancel(request: HttpRequest, pk) -> HttpResponse:
    task = get_object_or_404(WorkTask, pk=pk)
    try:
        task = cancel_task(task)
    except ValidationError as exc:
        return _render_error(request, task.farm, {}, _error_text(exc))
    return _render_success(request, task.farm, f"Tarea {task.title} cancelada.")


def _render_error(
    request: HttpRequest,
    farm: Farm | None,
    overrides: dict,
    message: str,
) -> HttpResponse:
    return render(
        request,
        "workforce/dashboard.html",
        _workforce_context(
            request,
            farm=farm,
            overrides={**overrides, "workforce_error": message},
        ),
        status=422,
    )


def _render_success(request: HttpRequest, farm: Farm, message: str) -> HttpResponse:
    return render(
        request,
        "workforce/dashboard.html",
        _workforce_context(
            request,
            farm=farm,
            overrides={"workforce_message": message},
        ),
    )
