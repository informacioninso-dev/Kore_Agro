from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from apps.finance.models import RevenueEntry
from apps.health.services import withdrawal_active_on
from apps.herd.models import Animal, Farm, HerdGroup

from .models import MilkingSession, MilkYield


@dataclass(frozen=True)
class MilkRecord:
    liters: Decimal
    animal: Animal | None = None
    group: HerdGroup | None = None
    discard_reason: str = ""


@dataclass(frozen=True)
class MilkingResult:
    session: MilkingSession
    saleable_liters: Decimal
    discarded_liters: Decimal
    revenue: Decimal
    discarded_value: Decimal


@transaction.atomic
def register_milking(
    *,
    farm: Farm,
    milking_date,
    shift: str,
    records: list[MilkRecord],
    unit_price: Decimal | None = None,
    source_event_id: UUID | None = None,
    notes: str = "",
) -> MilkingSession:
    return register_milking_detailed(
        farm=farm,
        milking_date=milking_date,
        shift=shift,
        records=records,
        unit_price=unit_price,
        source_event_id=source_event_id,
        notes=notes,
    ).session


@transaction.atomic
def register_milking_detailed(
    *,
    farm: Farm,
    milking_date,
    shift: str,
    records: list[MilkRecord],
    unit_price: Decimal | None = None,
    source_event_id: UUID | None = None,
    notes: str = "",
) -> MilkingResult:
    """Register a milking and its economic impact.

    Milk produced by an animal under an active withdrawal is recorded for
    biological traceability but never becomes revenue: it is flagged as
    discarded and the lost value is reported by the finance engine.
    """
    if not records:
        raise ValueError("Milking requires at least one record.")

    price = unit_price if unit_price is not None else farm.default_milk_price
    session = MilkingSession.objects.create(
        farm=farm,
        milking_date=milking_date,
        shift=shift,
        source_event_id=source_event_id,
        notes=notes,
    )

    saleable_liters = Decimal("0")
    discarded_liters = Decimal("0")

    for record in records:
        if record.liters <= 0:
            raise ValueError("Milk liters must be positive.")
        if not record.animal and not record.group:
            raise ValueError("Milk record requires either animal or group.")

        group = record.group or (record.animal.current_group if record.animal else None)
        discard_reason = _discard_reason(record=record, milking_date=milking_date)

        MilkYield.objects.create(
            session=session,
            farm=farm,
            animal=record.animal,
            group=group,
            liters=record.liters,
            unit_price=price,
            is_discarded=bool(discard_reason),
            discard_reason=discard_reason,
        )

        if discard_reason:
            discarded_liters += record.liters
            continue

        saleable_liters += record.liters
        RevenueEntry.objects.create(
            farm=farm,
            group=group,
            animal=record.animal,
            revenue_type=RevenueEntry.RevenueType.MILK,
            revenue_date=milking_date,
            quantity=record.liters,
            unit_price=price,
            gross_amount=record.liters * price,
            source_event_id=source_event_id,
            notes="Venta operativa de leche",
        )

    return MilkingResult(
        session=session,
        saleable_liters=saleable_liters,
        discarded_liters=discarded_liters,
        revenue=saleable_liters * price,
        discarded_value=discarded_liters * price,
    )


def _discard_reason(*, record: MilkRecord, milking_date) -> str:
    if record.discard_reason:
        return record.discard_reason[:160]
    if not record.animal:
        return ""
    withdrawal = withdrawal_active_on(animal=record.animal, on_date=milking_date)
    if not withdrawal:
        return ""
    return f"Retiro de leche: {withdrawal.reason}"[:160]
