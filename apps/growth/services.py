from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.herd.models import Animal, Farm, HerdGroup

from .models import WeightRecord


@dataclass(frozen=True)
class GrowthMetric:
    animal: Animal
    latest: WeightRecord
    previous: WeightRecord | None
    gain_kg: Decimal | None
    days_between: int | None
    daily_gain: Decimal | None

    def projected_days_to(self, target_weight: Decimal) -> int | None:
        if self.latest.weight_kg >= target_weight:
            return 0
        if not self.daily_gain or self.daily_gain <= 0:
            return None
        remaining = target_weight - self.latest.weight_kg
        return int((remaining / self.daily_gain).to_integral_value(rounding=ROUND_CEILING))


@dataclass(frozen=True)
class GroupGrowthSummary:
    group: HerdGroup | None
    animals_weighed: int
    average_weight: Decimal
    average_daily_gain: Decimal | None


@transaction.atomic
def record_weight(
    *,
    farm: Farm,
    animal: Animal,
    weight_kg: Decimal,
    weighed_on=None,
    body_condition_score: Decimal | None = None,
    scale_identifier: str = "",
    operator=None,
    source_event_id: UUID | None = None,
    notes: str = "",
) -> WeightRecord:
    record = WeightRecord(
        farm=farm,
        animal=animal,
        group=animal.current_group,
        weighed_on=weighed_on or timezone.localdate(),
        weight_kg=weight_kg,
        body_condition_score=body_condition_score,
        scale_identifier=scale_identifier,
        operator=operator,
        source_event_id=source_event_id,
        notes=notes,
    )
    record.save()
    return record


def _metric(animal: Animal, records: list[WeightRecord]) -> GrowthMetric:
    latest = records[0]
    previous = records[1] if len(records) > 1 else None
    gain = None
    days = None
    daily_gain = None
    if previous:
        days = (latest.weighed_on - previous.weighed_on).days
        if days > 0:
            gain = latest.weight_kg - previous.weight_kg
            daily_gain = (gain / Decimal(days)).quantize(Decimal("0.001"))
    return GrowthMetric(
        animal=animal,
        latest=latest,
        previous=previous,
        gain_kg=gain,
        days_between=days,
        daily_gain=daily_gain,
    )


def get_animal_growth(animal: Animal) -> GrowthMetric | None:
    records = list(
        WeightRecord.objects.filter(animal=animal)
        .select_related("animal", "group", "farm")
        .order_by("-weighed_on", "-created_at")[:2]
    )
    return _metric(animal, records) if records else None


def get_growth_metrics(
    *,
    farm: Farm,
    group: HerdGroup | None = None,
) -> list[GrowthMetric]:
    queryset = WeightRecord.objects.filter(farm=farm, animal__is_active=True).select_related(
        "animal",
        "group",
        "farm",
    )
    if group:
        queryset = queryset.filter(group=group)
    records_by_animal: dict[UUID, list[WeightRecord]] = {}
    for record in queryset.order_by("animal_id", "-weighed_on", "-created_at"):
        records = records_by_animal.setdefault(record.animal_id, [])
        if len(records) < 2:
            records.append(record)
    metrics = [_metric(records[0].animal, records) for records in records_by_animal.values()]
    return sorted(metrics, key=lambda item: item.animal.tag)


def summarize_groups(metrics: list[GrowthMetric]) -> list[GroupGrowthSummary]:
    grouped: dict[UUID | None, list[GrowthMetric]] = {}
    for metric in metrics:
        grouped.setdefault(metric.latest.group_id, []).append(metric)

    summaries = []
    for rows in grouped.values():
        latest_weights = [row.latest.weight_kg for row in rows]
        daily_gains = [row.daily_gain for row in rows if row.daily_gain is not None]
        average_weight = (sum(latest_weights, Decimal("0")) / len(latest_weights)).quantize(
            Decimal("0.01")
        )
        average_daily_gain = None
        if daily_gains:
            average_daily_gain = (
                sum(daily_gains, Decimal("0")) / len(daily_gains)
            ).quantize(Decimal("0.001"))
        summaries.append(
            GroupGrowthSummary(
                group=rows[0].latest.group,
                animals_weighed=len(rows),
                average_weight=average_weight,
                average_daily_gain=average_daily_gain,
            )
        )
    return sorted(summaries, key=lambda item: item.group.name if item.group else "ZZZ")
