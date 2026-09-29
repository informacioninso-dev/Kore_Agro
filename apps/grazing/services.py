from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from apps.herd.models import Farm, HerdGroup

from .models import GrazingPeriod, Paddock


@dataclass(frozen=True)
class PaddockSummary:
    paddock: Paddock
    status: str
    status_label: str
    active_period: GrazingPeriod | None
    last_period: GrazingPeriod | None
    rest_days: int | None
    rest_days_remaining: int | None


@transaction.atomic
def start_grazing_period(
    *,
    farm: Farm,
    paddock: Paddock,
    group: HerdGroup,
    started_on: date | None = None,
    planned_end_on: date | None = None,
    head_count: int | None = None,
    entry_biomass_kg_ha: Decimal | None = None,
    source_event_id: UUID | None = None,
    notes: str = "",
) -> GrazingPeriod:
    paddock = Paddock.objects.select_for_update().get(pk=paddock.pk, is_active=True)
    group = HerdGroup.objects.select_for_update().get(pk=group.pk, is_active=True)
    if paddock.farm_id != farm.id or group.farm_id != farm.id:
        raise ValidationError("El potrero y el lote deben pertenecer a la misma hacienda.")
    if GrazingPeriod.objects.filter(paddock=paddock, ended_on__isnull=True).exists():
        raise ValidationError("El potrero ya esta ocupado.")
    if GrazingPeriod.objects.filter(group=group, ended_on__isnull=True).exists():
        raise ValidationError("El lote ya se encuentra en otro potrero.")

    effective_start = started_on or timezone.localdate()
    last_period = (
        GrazingPeriod.objects.filter(paddock=paddock, ended_on__isnull=False)
        .order_by("-ended_on")
        .first()
    )
    if last_period:
        rest_days = (effective_start - last_period.ended_on).days
        if rest_days < paddock.rest_target_days:
            remaining = paddock.rest_target_days - max(rest_days, 0)
            raise ValidationError(
                f"El potrero necesita {remaining} dia(s) adicionales de descanso."
            )

    effective_head_count = (
        head_count if head_count is not None else group.animals.filter(is_active=True).count()
    )
    if effective_head_count <= 0:
        raise ValidationError("Indica al menos un animal para iniciar la rotacion.")
    if paddock.capacity_animals and effective_head_count > paddock.capacity_animals:
        raise ValidationError(
            f"La capacidad declarada del potrero es {paddock.capacity_animals} animales."
        )

    period = GrazingPeriod(
        farm=farm,
        paddock=paddock,
        group=group,
        started_on=effective_start,
        planned_end_on=planned_end_on,
        head_count=effective_head_count,
        entry_biomass_kg_ha=entry_biomass_kg_ha,
        source_event_id=source_event_id,
        notes=notes,
    )
    period.save()
    return period


@transaction.atomic
def finish_grazing_period(
    period: GrazingPeriod,
    *,
    ended_on: date | None = None,
    exit_biomass_kg_ha: Decimal | None = None,
    notes: str = "",
) -> GrazingPeriod:
    period = GrazingPeriod.objects.select_for_update().get(pk=period.pk)
    if period.ended_on:
        raise ValidationError("Esta rotacion ya fue cerrada.")
    period.ended_on = ended_on or timezone.localdate()
    period.exit_biomass_kg_ha = exit_biomass_kg_ha
    if notes:
        period.notes = f"{period.notes} | {notes}".strip(" |")
    period.save()
    return period


def get_paddock_summaries(*, farm: Farm) -> list[PaddockSummary]:
    periods = GrazingPeriod.objects.select_related("group").order_by("-started_on", "-created_at")
    paddocks = Paddock.objects.filter(farm=farm, is_active=True).prefetch_related(
        Prefetch("grazing_periods", queryset=periods)
    )
    today = timezone.localdate()
    summaries = []
    for paddock in paddocks:
        paddock_periods = list(paddock.grazing_periods.all())
        active_period = next(
            (period for period in paddock_periods if period.ended_on is None), None
        )
        last_period = next((period for period in paddock_periods if period.ended_on), None)
        rest_days = None
        remaining = None
        if active_period:
            status = "occupied"
            status_label = "Ocupado"
        elif last_period:
            rest_days = max((today - last_period.ended_on).days, 0)
            remaining = max(paddock.rest_target_days - rest_days, 0)
            status = "available" if remaining == 0 else "resting"
            status_label = "Disponible" if remaining == 0 else "En descanso"
        else:
            status = "available"
            status_label = "Disponible"
        summaries.append(
            PaddockSummary(
                paddock=paddock,
                status=status,
                status_label=status_label,
                active_period=active_period,
                last_period=last_period,
                rest_days=rest_days,
                rest_days_remaining=remaining,
            )
        )
    return summaries
