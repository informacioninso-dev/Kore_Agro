from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import partial
from typing import Any
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.finance.services import record_animal_sale, record_operating_expense
from apps.grazing.models import GrazingPeriod, Paddock
from apps.grazing.services import finish_grazing_period, start_grazing_period
from apps.growth.services import record_weight
from apps.health.services import record_treatment
from apps.herd.models import Animal, Farm, HerdGroup
from apps.inventory.models import Input
from apps.inventory.services import (
    InsufficientStockError,
    adjust_stock,
    consume_input,
    receive_input,
)
from apps.milk.models import MilkingSession
from apps.milk.services import MilkRecord, register_milking
from apps.procurement.models import PurchaseOrderLine
from apps.procurement.services import receive_purchase_line
from apps.reproduction.models import ReproductionEvent
from apps.reproduction.services import record_reproduction_event
from apps.workforce.models import Worker, WorkTask
from apps.workforce.services import complete_task, start_task

from .models import IncomingEvent

MILK_MILKING_RECORDED = "milk.milking_recorded"
REPRODUCTION_HEAT_RECORDED = "reproduction.heat_recorded"
REPRODUCTION_SERVICE_RECORDED = "reproduction.service_recorded"
REPRODUCTION_CALVING_RECORDED = "reproduction.calving_recorded"
REPRODUCTION_DRY_OFF_RECORDED = "reproduction.dry_off_recorded"
HEALTH_TREATMENT_RECORDED = "health.treatment_recorded"
INVENTORY_INPUT_CONSUMED = "inventory.input_consumed"
INVENTORY_INPUT_RECEIVED = "inventory.input_received"
INVENTORY_STOCK_ADJUSTED = "inventory.stock_adjusted"
FINANCE_EXPENSE_RECORDED = "finance.expense_recorded"
HERD_ANIMAL_SOLD = "herd.animal_sold"
GROWTH_WEIGHT_RECORDED = "growth.weight_recorded"
GRAZING_ROTATION_STARTED = "grazing.rotation_started"
GRAZING_ROTATION_FINISHED = "grazing.rotation_finished"
WORKFORCE_TASK_STARTED = "workforce.task_started"
WORKFORCE_TASK_COMPLETED = "workforce.task_completed"
PROCUREMENT_PURCHASE_RECEIVED = "procurement.purchase_received"
SUPPORTED_SCHEMA_VERSIONS = frozenset({1})
EVENT_CAPABILITIES = {
    MILK_MILKING_RECORDED: "milk",
    REPRODUCTION_HEAT_RECORDED: "reproduction",
    REPRODUCTION_SERVICE_RECORDED: "reproduction",
    REPRODUCTION_CALVING_RECORDED: "reproduction",
    REPRODUCTION_DRY_OFF_RECORDED: "reproduction",
    HEALTH_TREATMENT_RECORDED: "health",
    INVENTORY_INPUT_CONSUMED: "inventory",
    INVENTORY_INPUT_RECEIVED: "inventory",
    INVENTORY_STOCK_ADJUSTED: "inventory",
    FINANCE_EXPENSE_RECORDED: "finance",
    HERD_ANIMAL_SOLD: "finance",
    GROWTH_WEIGHT_RECORDED: "growth",
    GRAZING_ROTATION_STARTED: "grazing",
    GRAZING_ROTATION_FINISHED: "grazing",
    WORKFORCE_TASK_STARTED: "workforce",
    WORKFORCE_TASK_COMPLETED: "workforce",
    PROCUREMENT_PURCHASE_RECEIVED: "procurement",
}
EVENT_PERMISSIONS = {
    PROCUREMENT_PURCHASE_RECEIVED: "procurement.receive_purchaseorder",
}


@dataclass(frozen=True)
class ActionEventMessage:
    event_id: UUID
    device_id: UUID
    actor_id: UUID | None
    tenant_id: UUID | None
    client_sequence: int
    schema_version: int
    event_type: str
    occurred_at: datetime
    payload: dict[str, Any]


@dataclass(frozen=True)
class ActionEventResult:
    event_id: UUID
    status: str
    detail: str = ""
    retryable: bool = False
    resolution: str = ""


def process_action_queue(
    events: list[ActionEventMessage],
    *,
    allowed_farm_ids: set[UUID] | None = None,
    allowed_capabilities: set[str] | None = None,
    allowed_worker_ids: set[UUID] | None = None,
    allowed_permissions: set[str] | None = None,
) -> list[ActionEventResult]:
    ordered_events = sorted(events, key=lambda item: item.client_sequence)
    results = []
    blocked_by = None
    for event in ordered_events:
        if blocked_by:
            results.append(
                ActionEventResult(
                    event_id=event.event_id,
                    status="blocked",
                    detail=f"Blocked by event {blocked_by}.",
                    retryable=True,
                    resolution="Resolve the earlier event, then retry the queue.",
                )
            )
            continue
        result = process_action_event(
            event,
            allowed_farm_ids=allowed_farm_ids,
            allowed_capabilities=allowed_capabilities,
            allowed_worker_ids=allowed_worker_ids,
            allowed_permissions=allowed_permissions,
        )
        results.append(result)
        if result.status in {"failed", "conflict"}:
            blocked_by = event.event_id
    return results


def process_action_event(
    message: ActionEventMessage,
    *,
    allowed_farm_ids: set[UUID] | None = None,
    allowed_capabilities: set[str] | None = None,
    allowed_worker_ids: set[UUID] | None = None,
    allowed_permissions: set[str] | None = None,
) -> ActionEventResult:
    try:
        _validate_message_envelope(message)
        _validate_event_capability(message, allowed_capabilities)
        _validate_farm_access(message, allowed_farm_ids)
        _validate_workforce_access(message, allowed_worker_ids)
        _validate_event_permission(message, allowed_permissions)
    except (ValidationError, ValueError, TypeError) as exc:
        return ActionEventResult(
            event_id=message.event_id,
            status="failed",
            detail=str(exc),
            resolution="Create a corrected event before retrying the queue.",
        )

    with transaction.atomic():
        incoming = _lock_or_register_event(message)
        if not _matches_stored_event(incoming, message):
            return ActionEventResult(
                event_id=message.event_id,
                status="conflict",
                detail="The event_id was already used with different data.",
                resolution="Create a new event instead of reusing this event_id.",
            )
        if incoming.status == IncomingEvent.Status.CONFLICT:
            return ActionEventResult(
                event_id=message.event_id,
                status="conflict",
                detail=incoming.error_message or "client_sequence_already_used",
                resolution="Create a new event with the next device sequence.",
            )
        if incoming.status == IncomingEvent.Status.PROCESSED:
            return ActionEventResult(
                event_id=message.event_id,
                status="acked",
                detail="already_processed",
            )

        incoming.mark_processing()
        try:
            with transaction.atomic():
                _validate_event(incoming)
                _dispatch(incoming)
        except InsufficientStockError as exc:
            return _process_expected_failure(incoming, exc)
        except (ObjectDoesNotExist, ValidationError, ValueError, KeyError) as exc:
            return _process_expected_failure(incoming, exc)
        except IntegrityError as exc:
            return _process_integrity_conflict(incoming, exc)
        incoming.mark_processed()
        return ActionEventResult(event_id=message.event_id, status="acked")


def _validate_farm_access(
    message: ActionEventMessage,
    allowed_farm_ids: set[UUID] | None,
) -> None:
    if allowed_farm_ids is None:
        return
    raw_farm_id = message.payload.get("farm_id")
    try:
        farm_id = UUID(str(raw_farm_id))
    except (TypeError, ValueError) as exc:
        raise ValidationError("farm_id is required and must be a UUID.") from exc
    if farm_id not in allowed_farm_ids:
        raise ValidationError("No tienes acceso a la hacienda indicada.")


def _validate_event_capability(
    message: ActionEventMessage,
    allowed_capabilities: set[str] | None,
) -> None:
    if allowed_capabilities is None:
        return
    required = EVENT_CAPABILITIES.get(message.event_type)
    if required and required not in allowed_capabilities:
        raise ValidationError(
            f"La capacidad '{required}' no esta habilitada para esta organizacion."
        )


def _validate_event_permission(
    message: ActionEventMessage,
    allowed_permissions: set[str] | None,
) -> None:
    if allowed_permissions is None:
        return
    required = EVENT_PERMISSIONS.get(message.event_type)
    if required and required not in allowed_permissions:
        raise ValidationError("No tienes permiso para ejecutar esta accion.")


def _validate_workforce_access(
    message: ActionEventMessage,
    allowed_worker_ids: set[UUID] | None,
) -> None:
    if allowed_worker_ids is None or message.event_type not in {
        WORKFORCE_TASK_STARTED,
        WORKFORCE_TASK_COMPLETED,
    }:
        return
    task_id = message.payload.get("task_id")
    if not task_id:
        raise ValidationError("task_id is required.")
    task = WorkTask.objects.only("assigned_to_id").get(pk=task_id)
    if task.assigned_to_id and task.assigned_to_id not in allowed_worker_ids:
        raise ValidationError("No tienes acceso a la tarea indicada.")
    worker_id = message.payload.get("worker_id")
    if worker_id:
        try:
            parsed_worker_id = UUID(str(worker_id))
        except (TypeError, ValueError) as exc:
            raise ValidationError("worker_id must be a UUID.") from exc
        if parsed_worker_id not in allowed_worker_ids:
            raise ValidationError("No puedes registrar trabajo a nombre de otra persona.")


def _process_expected_failure(incoming: IncomingEvent, exc: Exception) -> ActionEventResult:
    code = (
        "insufficient_stock" if isinstance(exc, InsufficientStockError) else exc.__class__.__name__
    )
    incoming.mark_failed(code=code, message=str(exc))
    resolution = (
        "Receive or adjust stock, then retry this event."
        if isinstance(exc, InsufficientStockError)
        else "Correct the missing or invalid data, then retry this event."
    )
    return ActionEventResult(
        event_id=incoming.event_id,
        status="failed",
        detail=str(exc),
        retryable=True,
        resolution=resolution,
    )


def _process_integrity_conflict(
    incoming: IncomingEvent,
    exc: IntegrityError,
) -> ActionEventResult:
    detail = "This event conflicts with data already registered."
    incoming.mark_failed(code="integrity_conflict", message=str(exc))
    return ActionEventResult(
        event_id=incoming.event_id,
        status="conflict",
        detail=detail,
        resolution="Review the existing record and create a corrected event if needed.",
    )


def _lock_or_register_event(message: ActionEventMessage) -> IncomingEvent:
    incoming = IncomingEvent.objects.select_for_update().filter(event_id=message.event_id).first()
    if incoming:
        return incoming

    sequence_owner = _sequence_owner(message)
    if sequence_owner:
        return _create_sequence_conflict(message, sequence_owner)

    try:
        with transaction.atomic():
            return IncomingEvent.objects.create(
                event_id=message.event_id,
                **_message_defaults(message),
            )
    except IntegrityError:
        incoming = (
            IncomingEvent.objects.select_for_update().filter(event_id=message.event_id).first()
        )
        if incoming:
            return incoming
        sequence_owner = _sequence_owner(message)
        if sequence_owner:
            return _create_sequence_conflict(message, sequence_owner)
        raise


def _sequence_owner(message: ActionEventMessage) -> IncomingEvent | None:
    return (
        IncomingEvent.objects.select_for_update()
        .exclude(status=IncomingEvent.Status.CONFLICT)
        .filter(device_id=message.device_id, client_sequence=message.client_sequence)
        .first()
    )


def _create_sequence_conflict(
    message: ActionEventMessage,
    sequence_owner: IncomingEvent,
) -> IncomingEvent:
    detail = f"client_sequence_already_used_by:{sequence_owner.event_id}"
    defaults = _message_defaults(message)
    defaults.update(
        status=IncomingEvent.Status.CONFLICT,
        error_code="client_sequence_reused",
        error_message=detail,
    )
    try:
        with transaction.atomic():
            return IncomingEvent.objects.create(event_id=message.event_id, **defaults)
    except IntegrityError:
        return IncomingEvent.objects.select_for_update().get(event_id=message.event_id)


def _message_defaults(message: ActionEventMessage) -> dict[str, Any]:
    return {
        "tenant_id": message.tenant_id,
        "device_id": message.device_id,
        "actor_id": message.actor_id,
        "client_sequence": message.client_sequence,
        "schema_version": message.schema_version,
        "event_type": message.event_type,
        "occurred_at": message.occurred_at,
        "payload": message.payload,
        "status": IncomingEvent.Status.RECEIVED,
    }


def _matches_stored_event(incoming: IncomingEvent, message: ActionEventMessage) -> bool:
    return all(
        (
            incoming.tenant_id == message.tenant_id,
            incoming.device_id == message.device_id,
            incoming.actor_id == message.actor_id,
            incoming.client_sequence == message.client_sequence,
            incoming.schema_version == message.schema_version,
            incoming.event_type == message.event_type,
            incoming.occurred_at == message.occurred_at,
            incoming.payload == message.payload,
        )
    )


def _validate_message_envelope(message: ActionEventMessage) -> None:
    if not isinstance(message.client_sequence, int) or isinstance(message.client_sequence, bool):
        raise ValidationError("client_sequence must be an integer.")
    if message.client_sequence <= 0:
        raise ValidationError("client_sequence must be positive.")
    if not isinstance(message.schema_version, int) or isinstance(message.schema_version, bool):
        raise ValidationError("schema_version must be an integer.")
    if not isinstance(message.event_type, str) or not message.event_type.strip():
        raise ValidationError("event_type is required.")
    if len(message.event_type) > 100:
        raise ValidationError("event_type cannot exceed 100 characters.")
    if not isinstance(message.payload, dict):
        raise ValidationError("payload must be an object.")
    if not isinstance(message.occurred_at, datetime) or timezone.is_naive(message.occurred_at):
        raise ValidationError("occurred_at must include a timezone.")


def _validate_event(event: IncomingEvent) -> None:
    if event.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValidationError(f"Unsupported schema_version: {event.schema_version}.")
    if event.event_type not in _HANDLERS:
        raise ValidationError(f"Unsupported event type: {event.event_type}")


def _dispatch(event: IncomingEvent) -> None:
    handler = _HANDLERS.get(event.event_type)
    if handler is None:
        raise ValueError(f"Unsupported event type: {event.event_type}")
    handler(event)


def _handle_milking(event: IncomingEvent) -> MilkingSession:
    payload = event.payload
    farm = _get_farm(payload)
    milking_date = (
        _payload_date(payload.get("milking_date")) or timezone.localtime(event.occurred_at).date()
    )
    shift = payload.get("shift") or MilkingSession.Shift.TOTAL_DAY
    if shift not in MilkingSession.Shift.values:
        raise ValidationError(f"Invalid milking shift: {shift}.")
    unit_price = _payload_decimal(payload, "unit_price", required=False, minimum=Decimal("0"))
    records = []
    payload_records = payload.get("records")
    if not isinstance(payload_records, list) or not payload_records:
        raise ValidationError("records must contain at least one milk record.")

    for record in payload_records:
        if not isinstance(record, dict):
            raise ValidationError("Each milk record must be an object.")
        animal = _get_animal(record, farm=farm, required=False)
        group = _get_group(record, farm=farm, required=False)
        if not animal and not group:
            raise ValidationError("Milk record requires animal_id/tag or group_id/name.")
        records.append(
            MilkRecord(
                animal=animal,
                group=group,
                liters=_payload_decimal(record, "liters", minimum=Decimal("0"), exclusive=True),
            )
        )

    return register_milking(
        farm=farm,
        milking_date=milking_date,
        shift=shift,
        records=records,
        unit_price=unit_price,
        source_event_id=event.event_id,
        notes=payload.get("notes", ""),
    )


def _handle_reproduction(event: IncomingEvent, event_type: str) -> ReproductionEvent:
    payload = event.payload
    farm = _get_farm(payload)
    animal = _get_animal(payload, farm=farm)
    occurred_on = (
        _payload_date(payload.get("occurred_on")) or timezone.localtime(event.occurred_at).date()
    )
    service_type = payload.get("service_type")
    if service_type and service_type not in ReproductionEvent.ServiceType.values:
        raise ValidationError(f"Invalid service_type: {service_type}.")
    calf_sex = payload.get("calf_sex")
    if calf_sex and calf_sex not in Animal.Sex.values:
        raise ValidationError(f"Invalid calf_sex: {calf_sex}.")

    return record_reproduction_event(
        farm=farm,
        animal=animal,
        event_type=event_type,
        occurred_on=occurred_on,
        source_event_id=event.event_id,
        payload=payload,
    )


def _handle_treatment(event: IncomingEvent):
    payload = event.payload
    farm = _get_farm(payload)
    animal = _get_animal(payload, farm=farm)
    input_ = _get_input(payload, required=False)
    diagnosis = payload.get("diagnosis")
    if not isinstance(diagnosis, str) or not diagnosis.strip():
        raise ValidationError("diagnosis is required.")
    quantity = _payload_decimal(
        payload,
        "quantity",
        required=False,
        minimum=Decimal("0"),
        exclusive=True,
    )
    withdrawal_hours = _payload_nonnegative_int(payload, "milk_withdrawal_hours")
    if quantity is not None and input_ is None:
        raise ValidationError("input_id, sku or input_name is required when quantity is provided.")

    return record_treatment(
        farm=farm,
        animal=animal,
        diagnosis=diagnosis.strip(),
        started_at=event.occurred_at,
        input_=input_,
        quantity=quantity,
        dosage=payload.get("dosage", ""),
        milk_withdrawal_hours=withdrawal_hours,
        source_event_id=event.event_id,
        notes=payload.get("notes", ""),
    )


def _handle_input_consumed(event: IncomingEvent):
    payload = event.payload
    farm = _get_farm(payload)
    animal = _get_animal(payload, farm=farm, required=False)
    group = _get_group(payload, farm=farm, required=False)
    input_ = _get_input(payload)
    quantity = _payload_decimal(payload, "quantity", minimum=Decimal("0"), exclusive=True)

    return consume_input(
        farm=farm,
        input_=input_,
        quantity=quantity,
        occurred_at=event.occurred_at,
        source_event_id=event.event_id,
        animal=animal,
        group=group,
        notes=payload.get("notes", ""),
    )


def _handle_input_received(event: IncomingEvent):
    payload = event.payload
    farm = _get_farm(payload)
    input_ = _get_input(payload)

    return receive_input(
        farm=farm,
        input_=input_,
        quantity=_payload_decimal(payload, "quantity", minimum=Decimal("0"), exclusive=True),
        unit_cost=_payload_decimal(payload, "unit_cost", required=False, minimum=Decimal("0")),
        occurred_at=event.occurred_at,
        lot_code=payload.get("lot_code", ""),
        expires_on=_payload_date(payload.get("expires_on")),
        source_event_id=event.event_id,
        notes=payload.get("notes", ""),
    )


def _handle_stock_adjusted(event: IncomingEvent):
    payload = event.payload
    farm = _get_farm(payload)
    input_ = _get_input(payload)
    animal = _get_animal(payload, farm=farm, required=False)
    group = _get_group(payload, farm=farm, required=False)

    return adjust_stock(
        farm=farm,
        input_=input_,
        quantity_delta=_payload_decimal(payload, "quantity_delta", nonzero=True),
        occurred_at=event.occurred_at,
        reason=payload.get("reason", ""),
        animal=animal,
        group=group,
        source_event_id=event.event_id,
    )


def _handle_expense_recorded(event: IncomingEvent):
    payload = event.payload
    farm = _get_farm(payload)
    animal = _get_animal(payload, farm=farm, required=False)
    group = _get_group(payload, farm=farm, required=False)

    return record_operating_expense(
        farm=farm,
        amount=_payload_decimal(payload, "amount", minimum=Decimal("0"), exclusive=True),
        cost_type=payload.get("cost_type", "other"),
        cost_date=_payload_date(payload.get("cost_date"))
        or timezone.localtime(event.occurred_at).date(),
        group=group,
        animal=animal,
        source_event_id=event.event_id,
        notes=payload.get("notes", ""),
    )


def _handle_animal_sold(event: IncomingEvent):
    payload = event.payload
    farm = _get_farm(payload)
    animal = _get_animal(payload, farm=farm)

    return record_animal_sale(
        farm=farm,
        animal=animal,
        amount=_payload_decimal(payload, "amount", minimum=Decimal("0"), exclusive=True),
        sale_date=_payload_date(payload.get("sale_date"))
        or timezone.localtime(event.occurred_at).date(),
        source_event_id=event.event_id,
        notes=payload.get("notes", ""),
    )


def _handle_weight_recorded(event: IncomingEvent):
    payload = event.payload
    farm = _get_farm(payload)
    animal = _get_animal(payload, farm=farm)
    body_condition_score = _payload_decimal(
        payload,
        "body_condition_score",
        required=False,
        minimum=Decimal("1"),
    )
    if body_condition_score is not None and body_condition_score > Decimal("5"):
        raise ValidationError("body_condition_score must be at most 5.")

    return record_weight(
        farm=farm,
        animal=animal,
        weight_kg=_payload_decimal(
            payload,
            "weight_kg",
            minimum=Decimal("0"),
            exclusive=True,
        ),
        weighed_on=_payload_date(payload.get("weighed_on"))
        or timezone.localtime(event.occurred_at).date(),
        body_condition_score=body_condition_score,
        scale_identifier=payload.get("scale_identifier", ""),
        source_event_id=event.event_id,
        notes=payload.get("notes", ""),
    )


def _handle_grazing_started(event: IncomingEvent):
    payload = event.payload
    farm = _get_farm(payload)
    paddock = Paddock.objects.get(id=payload.get("paddock_id"), farm=farm, is_active=True)
    group = _get_group(payload, farm=farm)

    return start_grazing_period(
        farm=farm,
        paddock=paddock,
        group=group,
        started_on=_payload_date(payload.get("started_on"))
        or timezone.localtime(event.occurred_at).date(),
        planned_end_on=_payload_date(payload.get("planned_end_on")),
        head_count=_payload_nonnegative_int(payload, "head_count"),
        entry_biomass_kg_ha=_payload_decimal(
            payload,
            "entry_biomass_kg_ha",
            required=False,
            minimum=Decimal("0"),
            exclusive=True,
        ),
        source_event_id=event.event_id,
        notes=payload.get("notes", ""),
    )


def _handle_grazing_finished(event: IncomingEvent):
    payload = event.payload
    farm = _get_farm(payload)
    period_id = payload.get("grazing_period_id")
    if not period_id:
        raise ValidationError("grazing_period_id is required.")
    period = GrazingPeriod.objects.get(id=period_id, farm=farm)

    return finish_grazing_period(
        period,
        ended_on=_payload_date(payload.get("ended_on"))
        or timezone.localtime(event.occurred_at).date(),
        exit_biomass_kg_ha=_payload_decimal(
            payload,
            "exit_biomass_kg_ha",
            required=False,
            minimum=Decimal("0"),
            exclusive=True,
        ),
        notes=payload.get("notes", ""),
    )


def _workforce_task_and_worker(payload: dict[str, Any]) -> tuple[WorkTask, Worker | None]:
    farm = _get_farm(payload)
    task_id = payload.get("task_id")
    if not task_id:
        raise ValidationError("task_id is required.")
    task = WorkTask.objects.get(id=task_id, farm=farm)
    worker = None
    if worker_id := payload.get("worker_id"):
        worker = Worker.objects.get(id=worker_id, farm=farm, is_active=True)
    return task, worker


def _handle_task_started(event: IncomingEvent):
    task, worker = _workforce_task_and_worker(event.payload)
    return start_task(task, worker=worker, started_at=event.occurred_at)


def _handle_task_completed(event: IncomingEvent):
    task, worker = _workforce_task_and_worker(event.payload)
    return complete_task(
        task,
        worker=worker,
        hours=_payload_decimal(
            event.payload,
            "hours",
            minimum=Decimal("0"),
            exclusive=True,
        ),
        completed_at=event.occurred_at,
        source_event_id=event.event_id,
        notes=event.payload.get("notes", ""),
    )


def _handle_purchase_received(event: IncomingEvent):
    payload = event.payload
    farm = _get_farm(payload)
    order_line_id = payload.get("order_line_id")
    if not order_line_id:
        raise ValidationError("order_line_id is required.")
    order_line = PurchaseOrderLine.objects.select_related("purchase_order").get(
        pk=order_line_id,
        purchase_order__farm=farm,
    )
    return receive_purchase_line(
        order_line=order_line,
        quantity=_payload_decimal(payload, "quantity", minimum=Decimal("0"), exclusive=True),
        received_at=event.occurred_at,
        lot_code=payload.get("lot_code", ""),
        expires_on=_payload_date(payload.get("expires_on")),
        supplier_document=payload.get("supplier_document", ""),
        source_event_id=event.event_id,
        notes=payload.get("notes", ""),
    )


_HANDLERS = {
    MILK_MILKING_RECORDED: _handle_milking,
    REPRODUCTION_HEAT_RECORDED: partial(
        _handle_reproduction,
        event_type=ReproductionEvent.EventType.HEAT,
    ),
    REPRODUCTION_SERVICE_RECORDED: partial(
        _handle_reproduction,
        event_type=ReproductionEvent.EventType.SERVICE,
    ),
    REPRODUCTION_CALVING_RECORDED: partial(
        _handle_reproduction,
        event_type=ReproductionEvent.EventType.CALVING,
    ),
    REPRODUCTION_DRY_OFF_RECORDED: partial(
        _handle_reproduction,
        event_type=ReproductionEvent.EventType.DRY_OFF,
    ),
    HEALTH_TREATMENT_RECORDED: _handle_treatment,
    INVENTORY_INPUT_CONSUMED: _handle_input_consumed,
    INVENTORY_INPUT_RECEIVED: _handle_input_received,
    INVENTORY_STOCK_ADJUSTED: _handle_stock_adjusted,
    FINANCE_EXPENSE_RECORDED: _handle_expense_recorded,
    HERD_ANIMAL_SOLD: _handle_animal_sold,
    GROWTH_WEIGHT_RECORDED: _handle_weight_recorded,
    GRAZING_ROTATION_STARTED: _handle_grazing_started,
    GRAZING_ROTATION_FINISHED: _handle_grazing_finished,
    WORKFORCE_TASK_STARTED: _handle_task_started,
    WORKFORCE_TASK_COMPLETED: _handle_task_completed,
    PROCUREMENT_PURCHASE_RECEIVED: _handle_purchase_received,
}

SUPPORTED_EVENT_TYPES = tuple(_HANDLERS)


def _get_farm(payload: dict[str, Any]) -> Farm:
    if farm_id := payload.get("farm_id"):
        return Farm.objects.get(id=farm_id)
    raise ValidationError("farm_id is required.")


def _get_animal(payload: dict[str, Any], *, farm: Farm, required: bool = True) -> Animal | None:
    if animal_id := payload.get("animal_id"):
        return Animal.objects.get(id=animal_id, farm=farm)
    if animal_tag := payload.get("animal_tag"):
        return Animal.objects.get(tag=animal_tag, farm=farm)
    if required:
        raise ValueError("animal_id or animal_tag is required.")
    return None


def _get_group(payload: dict[str, Any], *, farm: Farm, required: bool = True) -> HerdGroup | None:
    if group_id := payload.get("group_id"):
        return HerdGroup.objects.get(id=group_id, farm=farm)
    if group_name := payload.get("group_name"):
        return HerdGroup.objects.get(name=group_name, farm=farm)
    if required:
        raise ValueError("group_id or group_name is required.")
    return None


def _get_input(payload: dict[str, Any], *, required: bool = True) -> Input | None:
    if input_id := payload.get("input_id"):
        return Input.objects.get(id=input_id)
    if sku := payload.get("sku"):
        return Input.objects.get(sku=sku)
    if input_name := payload.get("input_name"):
        return Input.objects.get(name=input_name)
    if required:
        raise ValueError("input_id, sku or input_name is required.")
    return None


def _payload_date(value):
    if not value:
        return None
    if hasattr(value, "date") and not isinstance(value, str):
        return value.date()
    try:
        parsed = parse_date(str(value))
    except ValueError as exc:
        raise ValidationError(f"Invalid date: {value}.") from exc
    if parsed is None:
        raise ValidationError(f"Invalid date: {value}.")
    return parsed


def _payload_decimal(
    payload: dict[str, Any],
    field: str,
    *,
    required: bool = True,
    minimum: Decimal | None = None,
    exclusive: bool = False,
    nonzero: bool = False,
) -> Decimal | None:
    value = payload.get(field)
    if value is None or value == "":
        if required:
            raise ValidationError(f"{field} is required.")
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be a decimal number.") from exc
    if not number.is_finite():
        raise ValidationError(f"{field} must be a finite decimal number.")
    if minimum is not None:
        invalid = number <= minimum if exclusive else number < minimum
        if invalid:
            comparator = "greater than" if exclusive else "at least"
            raise ValidationError(f"{field} must be {comparator} {minimum}.")
    if nonzero and number == 0:
        raise ValidationError(f"{field} cannot be zero.")
    return number


def _payload_nonnegative_int(payload: dict[str, Any], field: str) -> int | None:
    value = payload.get(field)
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be a non-negative integer.") from exc
    if isinstance(value, float) and not value.is_integer():
        raise ValidationError(f"{field} must be a non-negative integer.")
    if isinstance(value, str) and str(number) != value.strip():
        raise ValidationError(f"{field} must be a non-negative integer.")
    if number < 0:
        raise ValidationError(f"{field} must be a non-negative integer.")
    return number
