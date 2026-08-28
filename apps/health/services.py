from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.herd.models import Animal, Farm
from apps.inventory.models import Input
from apps.inventory.services import consume_input

from .models import MilkWithdrawal, Treatment


@transaction.atomic
def record_treatment(
    *,
    farm: Farm,
    animal: Animal,
    diagnosis: str,
    started_at,
    input_: Input | None = None,
    quantity: Decimal | None = None,
    dosage: str = "",
    milk_withdrawal_hours: int | None = None,
    source_event_id: UUID | None = None,
    notes: str = "",
) -> Treatment:
    withdrawal_hours = milk_withdrawal_hours
    if withdrawal_hours is None and input_:
        withdrawal_hours = input_.milk_withdrawal_hours

    withdrawal_until = None
    if withdrawal_hours:
        withdrawal_until = started_at + timedelta(hours=withdrawal_hours)

    treatment = Treatment.objects.create(
        farm=farm,
        animal=animal,
        group=animal.current_group,
        input=input_,
        diagnosis=diagnosis,
        dosage=dosage,
        started_at=started_at,
        milk_withdrawal_until=withdrawal_until,
        source_event_id=source_event_id,
        notes=notes,
    )

    if input_ and quantity:
        consume_input(
            farm=farm,
            input_=input_,
            quantity=quantity,
            occurred_at=started_at,
            source_event_id=source_event_id,
            animal=animal,
            group=animal.current_group,
            notes=f"Tratamiento: {diagnosis}",
        )

    if withdrawal_until:
        MilkWithdrawal.objects.create(
            farm=farm,
            animal=animal,
            treatment=treatment,
            starts_at=started_at,
            ends_at=withdrawal_until,
            reason=diagnosis,
            source_event_id=source_event_id,
        )

    return treatment


def active_milk_withdrawals(now=None):
    now = now or timezone.now()
    return MilkWithdrawal.objects.filter(starts_at__lte=now, ends_at__gte=now).order_by("ends_at")


def withdrawal_active_on(*, animal: Animal, on_date) -> MilkWithdrawal | None:
    """Withdrawal that covers `on_date` for the animal, or None.

    Milking is captured per day, so the window is evaluated by local date: any
    overlap with the milking day discards that day's milk.
    """
    return (
        MilkWithdrawal.objects.filter(
            animal=animal,
            starts_at__date__lte=on_date,
            ends_at__date__gte=on_date,
        )
        .order_by("-ends_at")
        .first()
    )


def open_treatments():
    return Treatment.objects.filter(ended_at__isnull=True).order_by("started_at")

