from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from functools import partial
from typing import Any
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.finance.services import record_animal_sale, record_operating_expense
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
from apps.reproduction.models import ReproductionEvent
from apps.reproduction.services import record_reproduction_event

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


def process_action_queue(events: list[ActionEventMessage]) -> list[ActionEventResult]:
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
        result = process_action_event(event)
        results.append(result)
        if result.status in {"failed", "conflict"}:
            blocked_by = event.event_id
    return results


def process_action_event(message: ActionEventMessage) -> ActionEventResult:
    incoming, created = IncomingEvent.objects.get_or_create(
        event_id=message.event_id,
        defaults={
            "tenant_id": message.tenant_id,
            "device_id": message.device_id,
            "actor_id": message.actor_id,
            "client_sequence": message.client_sequence,
            "schema_version": message.schema_version,
            "event_type": message.event_type,
            "occurred_at": message.occurred_at,
            "payload": message.payload,
            "status": IncomingEvent.Status.RECEIVED,
        },
    )
    if not created and _event_contents_differ(incoming, message):
        return ActionEventResult(
            event_id=message.event_id,
            status="conflict",
            detail="The event_id was already used with different data.",
            resolution="Create a new event instead of reusing this event_id.",
        )
    if not created and incoming.status == IncomingEvent.Status.PROCESSED:
        return ActionEventResult(
            event_id=message.event_id,
            status="acked",
            detail="already_processed",
        )
    if not created and incoming.status == IncomingEvent.Status.CONFLICT:
        return ActionEventResult(
            event_id=message.event_id,
            status="conflict",
            detail=incoming.error_message,
            resolution="Create a corrected event with a new event_id.",
        )

    sequence_event = (
        IncomingEvent.objects.filter(
            device_id=message.device_id,
            client_sequence=message.client_sequence,
        )
        .exclude(event_id=message.event_id)
        .first()
    )
    if sequence_event:
        detail = f"Sequence {message.client_sequence} is already assigned to another event."
        incoming.mark_conflict(code="sequence_conflict", message=detail)
        return ActionEventResult(
            event_id=message.event_id,
            status="conflict",
            detail=detail,
            resolution="Create a new event with the next device sequence.",
        )

    incoming.mark_processing()
    try:
        with transaction.atomic():
            _dispatch(incoming)
    except InsufficientStockError as exc:
        incoming.mark_failed(code="insufficient_stock", message=str(exc))
        return ActionEventResult(
            event_id=message.event_id,
            status="failed",
            detail=str(exc),
            retryable=True,
            resolution="Receive or adjust stock, then retry this event.",
        )
    except (ObjectDoesNotExist, ValidationError, ValueError, KeyError) as exc:
        incoming.mark_failed(code=exc.__class__.__name__, message=str(exc))
        return ActionEventResult(
            event_id=message.event_id,
            status="failed",
            detail=str(exc),
            retryable=True,
            resolution="Correct the missing or invalid data, then retry this event.",
        )
    except IntegrityError:
        detail = "This event conflicts with data already registered."
        incoming.mark_conflict(code="integrity_conflict", message=detail)
        return ActionEventResult(
            event_id=message.event_id,
            status="conflict",
            detail=detail,
            resolution="Review the existing record and create a corrected event if needed.",
        )

    incoming.mark_processed()
    return ActionEventResult(event_id=message.event_id, status="acked")


def _event_contents_differ(incoming: IncomingEvent, message: ActionEventMessage) -> bool:
    return any(
        (
            incoming.device_id != message.device_id,
            incoming.client_sequence != message.client_sequence,
            incoming.event_type != message.event_type,
            incoming.occurred_at != message.occurred_at,
            incoming.payload != message.payload,
        )
    )


def _dispatch(event: IncomingEvent) -> None:
    handler = _HANDLERS.get(event.event_type)
    if handler is None:
        raise ValueError(f"Unsupported event type: {event.event_type}")
    handler(event)


def _handle_milking(event: IncomingEvent) -> MilkingSession:
    payload = event.payload
    farm = _get_farm(payload)
    milking_date = _payload_date(payload.get("milking_date")) or timezone.localtime(
        event.occurred_at
    ).date()
    shift = payload.get("shift") or MilkingSession.Shift.TOTAL_DAY
    unit_price = _decimal_or_none(payload.get("unit_price"))
    records = []

    for record in payload.get("records", []):
        animal = _get_animal(record, farm=farm, required=False)
        group = _get_group(record, farm=farm, required=False)
        records.append(
            MilkRecord(
                animal=animal,
                group=group,
                liters=Decimal(str(record["liters"])),
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
    occurred_on = _payload_date(payload.get("occurred_on")) or timezone.localtime(
        event.occurred_at
    ).date()

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
    quantity = _decimal_or_none(payload.get("quantity"))

    return record_treatment(
        farm=farm,
        animal=animal,
        diagnosis=payload["diagnosis"],
        started_at=event.occurred_at,
        input_=input_,
        quantity=quantity,
        dosage=payload.get("dosage", ""),
        milk_withdrawal_hours=payload.get("milk_withdrawal_hours"),
        source_event_id=event.event_id,
        notes=payload.get("notes", ""),
    )


def _handle_input_consumed(event: IncomingEvent):
    payload = event.payload
    farm = _get_farm(payload)
    animal = _get_animal(payload, farm=farm, required=False)
    group = _get_group(payload, farm=farm, required=False)
    input_ = _get_input(payload)
    quantity = Decimal(str(payload["quantity"]))

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
        quantity=Decimal(str(payload["quantity"])),
        unit_cost=_decimal_or_none(payload.get("unit_cost")),
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
        quantity_delta=Decimal(str(payload["quantity_delta"])),
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
        amount=Decimal(str(payload["amount"])),
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
        amount=Decimal(str(payload["amount"])),
        sale_date=_payload_date(payload.get("sale_date"))
        or timezone.localtime(event.occurred_at).date(),
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
}

SUPPORTED_EVENT_TYPES = tuple(_HANDLERS)


def _get_farm(payload: dict[str, Any]) -> Farm:
    if farm_id := payload.get("farm_id"):
        return Farm.objects.get(id=farm_id)
    farm = Farm.objects.filter(is_active=True).order_by("created_at").first()
    if not farm:
        raise ObjectDoesNotExist("No active farm found for tenant.")
    return farm


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
    return parse_date(str(value))


def _decimal_or_none(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))
