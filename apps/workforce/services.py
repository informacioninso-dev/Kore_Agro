from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.finance.models import CostAllocation
from apps.finance.services import record_operating_expense

from .models import Worker, WorkLog, WorkTask


def _validate_worker(task: WorkTask, worker: Worker | None) -> Worker:
    effective_worker = worker or task.assigned_to
    if not effective_worker:
        raise ValidationError("Selecciona un responsable para la tarea.")
    if not effective_worker.is_active or effective_worker.farm_id != task.farm_id:
        raise ValidationError("El trabajador no esta activo en esta hacienda.")
    if task.assigned_to_id and task.assigned_to_id != effective_worker.id:
        raise ValidationError("La tarea esta asignada a otro trabajador.")
    return effective_worker


@transaction.atomic
def start_task(
    task: WorkTask,
    *,
    worker: Worker | None = None,
    started_at: datetime | None = None,
) -> WorkTask:
    task = WorkTask.objects.select_for_update().get(pk=task.pk)
    if task.status == WorkTask.Status.COMPLETED:
        raise ValidationError("La tarea ya fue completada.")
    if task.status == WorkTask.Status.CANCELLED:
        raise ValidationError("La tarea esta cancelada.")
    effective_worker = _validate_worker(task, worker)
    task.assigned_to = effective_worker
    task.status = WorkTask.Status.IN_PROGRESS
    task.started_at = task.started_at or started_at or timezone.now()
    task.save(update_fields=["assigned_to", "status", "started_at", "updated_at"])
    return task


@transaction.atomic
def complete_task(
    task: WorkTask,
    *,
    worker: Worker | None = None,
    hours: Decimal,
    completed_at: datetime | None = None,
    source_event_id: UUID | None = None,
    notes: str = "",
) -> WorkLog:
    task = WorkTask.objects.select_for_update().get(pk=task.pk)
    if task.status == WorkTask.Status.COMPLETED:
        raise ValidationError("La tarea ya fue completada.")
    if task.status == WorkTask.Status.CANCELLED:
        raise ValidationError("La tarea esta cancelada.")
    effective_worker = _validate_worker(task, worker)
    worked_hours = Decimal(str(hours))
    if worked_hours <= 0:
        raise ValidationError("Las horas trabajadas deben ser mayores que cero.")

    effective_completed_at = completed_at or timezone.now()
    rate = effective_worker.hourly_rate
    labor_cost = (worked_hours * rate).quantize(Decimal("0.0001"))
    cost_allocation = None
    if labor_cost > 0:
        cost_allocation = record_operating_expense(
            farm=task.farm,
            group=task.group,
            animal=task.animal,
            amount=labor_cost,
            cost_type=CostAllocation.CostType.LABOR,
            cost_date=timezone.localtime(effective_completed_at).date(),
            source_event_id=source_event_id,
            notes=f"Tarea: {task.title} | {effective_worker.full_name}",
        )

    log = WorkLog.objects.create(
        task=task,
        worker=effective_worker,
        work_date=timezone.localtime(effective_completed_at).date(),
        hours=worked_hours,
        hourly_rate=rate,
        labor_cost=labor_cost,
        cost_allocation=cost_allocation,
        source_event_id=source_event_id,
        notes=notes,
    )
    task.assigned_to = effective_worker
    task.status = WorkTask.Status.COMPLETED
    task.started_at = task.started_at or effective_completed_at
    task.completed_at = effective_completed_at
    task.save(
        update_fields=[
            "assigned_to",
            "status",
            "started_at",
            "completed_at",
            "updated_at",
        ]
    )
    return log


@transaction.atomic
def cancel_task(task: WorkTask) -> WorkTask:
    task = WorkTask.objects.select_for_update().get(pk=task.pk)
    if task.status == WorkTask.Status.COMPLETED:
        raise ValidationError("Una tarea completada no puede cancelarse.")
    task.status = WorkTask.Status.CANCELLED
    task.cancelled_at = timezone.now()
    task.save(update_fields=["status", "cancelled_at", "updated_at"])
    return task
