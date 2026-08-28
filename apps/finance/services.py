from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.db.models import (
    DecimalField,
    ExpressionWrapper,
    F,
    Max,
    Q,
    QuerySet,
    Sum,
)
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.herd.models import Animal, Farm, HerdGroup
from apps.milk.models import MilkYield
from apps.sync.models import IncomingEvent

from .models import CostAllocation, OperatingPeriodSnapshot, RevenueEntry


@dataclass(frozen=True)
class OperatingPnl:
    liters: Decimal
    revenue: Decimal
    costs: Decimal
    net_profit: Decimal
    cost_per_liter: Decimal
    margin_pct: Decimal
    saleable_liters: Decimal = Decimal("0")
    discarded_liters: Decimal = Decimal("0")
    discarded_value: Decimal = Decimal("0")
    cost_per_saleable_liter: Decimal = Decimal("0")


@dataclass(frozen=True)
class PnlBreakdown:
    entity_id: UUID | None
    label: str
    pnl: OperatingPnl


@dataclass(frozen=True)
class DailyPnl:
    day: date
    pnl: OperatingPnl


@dataclass(frozen=True)
class CostBreakdown:
    cost_type: str
    label: str
    amount: Decimal
    percentage: Decimal


@dataclass(frozen=True)
class EventTraceLine:
    source_event_id: UUID
    occurred_on: date | None
    event_type: str
    status: str
    liters: Decimal
    revenue: Decimal
    costs: Decimal
    net_profit: Decimal
    discarded_liters: Decimal = Decimal("0")


@dataclass(frozen=True)
class FinancialExceptionLine:
    line_type: str
    occurred_on: date
    source_event_id: UUID | None
    target: str
    reason: str
    liters: Decimal
    amount: Decimal


def _sum_decimal(queryset, field: str) -> Decimal:
    return queryset.aggregate(total=Sum(field))["total"] or Decimal("0")


def _decimal(value) -> Decimal:
    return value or Decimal("0")


def _normalize_date(value, fallback: date) -> date:
    if value is None:
        return fallback
    if isinstance(value, str):
        parsed = parse_date(value)
        if parsed is None:
            raise ValueError(f"Invalid date: {value}")
        return parsed
    return value


def _date_window(start_date=None, end_date=None) -> tuple[date, date]:
    today = timezone.localdate()
    end = _normalize_date(end_date, today)
    start = _normalize_date(start_date, end.replace(day=1))
    if start > end:
        raise ValueError("start_date cannot be after end_date.")
    return start, end


def _gross_value_expression() -> ExpressionWrapper:
    return ExpressionWrapper(
        F("liters") * F("unit_price"),
        output_field=DecimalField(max_digits=18, decimal_places=4),
    )


@dataclass(frozen=True)
class MilkTotals:
    liters: Decimal
    discarded_liters: Decimal
    discarded_value: Decimal


def _milk_totals(milk_qs) -> MilkTotals:
    totals = milk_qs.aggregate(
        total=Sum("liters"),
        discarded=Sum("liters", filter=Q(is_discarded=True)),
        discarded_amount=Sum(_gross_value_expression(), filter=Q(is_discarded=True)),
    )
    return MilkTotals(
        liters=_decimal(totals["total"]),
        discarded_liters=_decimal(totals["discarded"]),
        discarded_value=_decimal(totals["discarded_amount"]),
    )


def _build_pnl(
    *,
    liters: Decimal,
    revenue: Decimal,
    costs: Decimal,
    discarded_liters: Decimal = Decimal("0"),
    discarded_value: Decimal = Decimal("0"),
) -> OperatingPnl:
    net_profit = revenue - costs
    saleable_liters = liters - discarded_liters
    return OperatingPnl(
        liters=liters,
        revenue=revenue,
        costs=costs,
        net_profit=net_profit,
        cost_per_liter=costs / liters if liters else Decimal("0"),
        margin_pct=(net_profit / revenue * Decimal("100")) if revenue else Decimal("0"),
        saleable_liters=saleable_liters,
        discarded_liters=discarded_liters,
        discarded_value=discarded_value,
        cost_per_saleable_liter=costs / saleable_liters if saleable_liters else Decimal("0"),
    )


def _scoped_querysets(
    *,
    farm: Farm | None = None,
    group: HerdGroup | None = None,
    animal: Animal | None = None,
    start_date=None,
    end_date=None,
) -> tuple[QuerySet, QuerySet, QuerySet]:
    start, end = _date_window(start_date=start_date, end_date=end_date)

    revenue_qs = RevenueEntry.objects.filter(
        revenue_date__gte=start,
        revenue_date__lte=end,
    )
    cost_qs = CostAllocation.objects.filter(cost_date__gte=start, cost_date__lte=end)
    milk_qs = MilkYield.objects.filter(
        session__milking_date__gte=start,
        session__milking_date__lte=end,
    )

    if farm:
        revenue_qs = revenue_qs.filter(farm=farm)
        cost_qs = cost_qs.filter(farm=farm)
        milk_qs = milk_qs.filter(farm=farm)

    if group:
        revenue_qs = revenue_qs.filter(group=group)
        cost_qs = cost_qs.filter(group=group)
        milk_qs = milk_qs.filter(group=group)

    if animal:
        revenue_qs = revenue_qs.filter(animal=animal)
        cost_qs = cost_qs.filter(animal=animal)
        milk_qs = milk_qs.filter(animal=animal)

    return revenue_qs, cost_qs, milk_qs


def get_operating_pnl(
    *,
    farm: Farm | None = None,
    group: HerdGroup | None = None,
    animal: Animal | None = None,
    start_date=None,
    end_date=None,
) -> OperatingPnl:
    revenue_qs, cost_qs, milk_qs = _scoped_querysets(
        farm=farm,
        group=group,
        animal=animal,
        start_date=start_date,
        end_date=end_date,
    )

    milk = _milk_totals(milk_qs)
    return _build_pnl(
        liters=milk.liters,
        revenue=_sum_decimal(revenue_qs, "gross_amount"),
        costs=_sum_decimal(cost_qs, "amount"),
        discarded_liters=milk.discarded_liters,
        discarded_value=milk.discarded_value,
    )


def get_daily_pnl(
    *,
    farm: Farm | None = None,
    group: HerdGroup | None = None,
    animal: Animal | None = None,
    start_date=None,
    end_date=None,
) -> list[DailyPnl]:
    revenue_qs, cost_qs, milk_qs = _scoped_querysets(
        farm=farm,
        group=group,
        animal=animal,
        start_date=start_date,
        end_date=end_date,
    )

    milk_by_date = {
        row["session__milking_date"]: row
        for row in milk_qs.values("session__milking_date").annotate(
            total=Sum("liters"),
            discarded=Sum("liters", filter=Q(is_discarded=True)),
            discarded_value=Sum(_gross_value_expression(), filter=Q(is_discarded=True)),
        )
    }
    revenue_by_date = {
        row["revenue_date"]: _decimal(row["total"])
        for row in revenue_qs.values("revenue_date").annotate(total=Sum("gross_amount"))
    }
    cost_by_date = {
        row["cost_date"]: _decimal(row["total"])
        for row in cost_qs.values("cost_date").annotate(total=Sum("amount"))
    }

    days = sorted(
        set(milk_by_date) | set(revenue_by_date) | set(cost_by_date),
        reverse=True,
    )
    empty_milk = {"total": None, "discarded": None, "discarded_value": None}

    return [
        DailyPnl(
            day=day,
            pnl=_build_pnl(
                liters=_decimal(milk_by_date.get(day, empty_milk)["total"]),
                revenue=revenue_by_date.get(day, Decimal("0")),
                costs=cost_by_date.get(day, Decimal("0")),
                discarded_liters=_decimal(milk_by_date.get(day, empty_milk)["discarded"]),
                discarded_value=_decimal(milk_by_date.get(day, empty_milk)["discarded_value"]),
            ),
        )
        for day in days
    ]


def get_group_pnl(
    *,
    farm: Farm | None,
    start_date=None,
    end_date=None,
) -> list[PnlBreakdown]:
    if not farm:
        return []

    groups = HerdGroup.objects.filter(farm=farm, is_active=True).order_by("name")
    rows = [
        PnlBreakdown(
            entity_id=group.id,
            label=group.name,
            pnl=get_operating_pnl(farm=farm, group=group, start_date=start_date, end_date=end_date),
        )
        for group in groups
    ]
    unassigned_pnl = _get_unassigned_group_pnl(
        farm=farm,
        start_date=start_date,
        end_date=end_date,
    )
    if _has_activity(unassigned_pnl):
        rows.append(PnlBreakdown(entity_id=None, label="Sin asignar", pnl=unassigned_pnl))
    return rows


def _get_unassigned_group_pnl(*, farm: Farm, start_date=None, end_date=None) -> OperatingPnl:
    revenue_qs, cost_qs, milk_qs = _scoped_querysets(
        farm=farm,
        start_date=start_date,
        end_date=end_date,
    )
    milk = _milk_totals(milk_qs.filter(group__isnull=True))
    return _build_pnl(
        liters=milk.liters,
        revenue=_sum_decimal(revenue_qs.filter(group__isnull=True), "gross_amount"),
        costs=_sum_decimal(cost_qs.filter(group__isnull=True), "amount"),
        discarded_liters=milk.discarded_liters,
        discarded_value=milk.discarded_value,
    )


def _has_activity(pnl: OperatingPnl) -> bool:
    return bool(pnl.liters or pnl.revenue or pnl.costs)


def get_animal_pnl(
    *,
    farm: Farm | None,
    group: HerdGroup | None = None,
    start_date=None,
    end_date=None,
) -> list[PnlBreakdown]:
    if not farm:
        return []

    animals = Animal.objects.select_related("current_group").filter(farm=farm, is_active=True)
    if group:
        animals = animals.filter(current_group=group)

    return [
        PnlBreakdown(
            entity_id=animal.id,
            label=f"{animal.tag} - {animal.name}" if animal.name else animal.tag,
            pnl=get_operating_pnl(
                farm=farm,
                group=group,
                animal=animal,
                start_date=start_date,
                end_date=end_date,
            ),
        )
        for animal in animals.order_by("tag")
    ]


def get_cost_breakdown(
    *,
    farm: Farm | None = None,
    group: HerdGroup | None = None,
    animal: Animal | None = None,
    start_date=None,
    end_date=None,
) -> list[CostBreakdown]:
    _, cost_qs, _ = _scoped_querysets(
        farm=farm,
        group=group,
        animal=animal,
        start_date=start_date,
        end_date=end_date,
    )
    total_cost = _sum_decimal(cost_qs, "amount")
    labels = dict(CostAllocation.CostType.choices)

    rows = (
        cost_qs.values("cost_type")
        .annotate(amount=Sum("amount"))
        .order_by("-amount", "cost_type")
    )
    return [
        CostBreakdown(
            cost_type=row["cost_type"],
            label=labels.get(row["cost_type"], row["cost_type"]),
            amount=_decimal(row["amount"]),
            percentage=(
                _decimal(row["amount"]) / total_cost * Decimal("100")
                if total_cost
                else Decimal("0")
            ),
        )
        for row in rows
    ]


def get_event_trace(
    *,
    farm: Farm | None = None,
    group: HerdGroup | None = None,
    animal: Animal | None = None,
    start_date=None,
    end_date=None,
    limit: int = 25,
) -> list[EventTraceLine]:
    revenue_qs, cost_qs, milk_qs = _scoped_querysets(
        farm=farm,
        group=group,
        animal=animal,
        start_date=start_date,
        end_date=end_date,
    )
    rows: dict[UUID, dict] = {}

    def row_for(source_event_id: UUID, occurred_on) -> dict:
        row = rows.setdefault(
            source_event_id,
            {
                "source_event_id": source_event_id,
                "occurred_on": occurred_on,
                "event_type": "manual/direct",
                "status": "applied",
                "liters": Decimal("0"),
                "discarded_liters": Decimal("0"),
                "revenue": Decimal("0"),
                "costs": Decimal("0"),
            },
        )
        if occurred_on and (row["occurred_on"] is None or occurred_on > row["occurred_on"]):
            row["occurred_on"] = occurred_on
        return row

    for row in (
        milk_qs.exclude(session__source_event_id__isnull=True)
        .values("session__source_event_id")
        .annotate(
            total=Sum("liters"),
            discarded=Sum("liters", filter=Q(is_discarded=True)),
            occurred_on=Max("session__milking_date"),
        )
    ):
        current = row_for(row["session__source_event_id"], row["occurred_on"])
        current["liters"] += _decimal(row["total"])
        current["discarded_liters"] += _decimal(row["discarded"])

    for row in (
        revenue_qs.exclude(source_event_id__isnull=True)
        .values("source_event_id")
        .annotate(revenue=Sum("gross_amount"), occurred_on=Max("revenue_date"))
    ):
        current = row_for(row["source_event_id"], row["occurred_on"])
        current["revenue"] += _decimal(row["revenue"])

    for row in (
        cost_qs.exclude(source_event_id__isnull=True)
        .values("source_event_id")
        .annotate(costs=Sum("amount"), occurred_on=Max("cost_date"))
    ):
        current = row_for(row["source_event_id"], row["occurred_on"])
        current["costs"] += _decimal(row["costs"])

    event_ids = list(rows)
    if event_ids:
        for event in IncomingEvent.objects.filter(event_id__in=event_ids).only(
            "event_id",
            "event_type",
            "status",
            "occurred_at",
        ):
            current = rows[event.event_id]
            current["event_type"] = event.event_type
            current["status"] = event.status
            if current["occurred_on"] is None:
                current["occurred_on"] = timezone.localtime(event.occurred_at).date()

    trace = [
        EventTraceLine(
            source_event_id=row["source_event_id"],
            occurred_on=row["occurred_on"],
            event_type=row["event_type"],
            status=row["status"],
            liters=row["liters"],
            revenue=row["revenue"],
            costs=row["costs"],
            net_profit=row["revenue"] - row["costs"],
            discarded_liters=row["discarded_liters"],
        )
        for row in rows.values()
    ]
    trace.sort(
        key=lambda line: (line.occurred_on or date.min, str(line.source_event_id)),
        reverse=True,
    )
    return trace[:limit]


def get_unassigned_financial_lines(
    *,
    farm: Farm | None = None,
    start_date=None,
    end_date=None,
    limit: int = 20,
) -> list[FinancialExceptionLine]:
    revenue_qs, cost_qs, _ = _scoped_querysets(
        farm=farm,
        start_date=start_date,
        end_date=end_date,
    )
    lines = []

    for entry in revenue_qs.filter(group__isnull=True).select_related("animal"):
        lines.append(
            FinancialExceptionLine(
                line_type="Ingreso",
                occurred_on=entry.revenue_date,
                source_event_id=entry.source_event_id,
                target=entry.animal.tag if entry.animal else "Hacienda",
                reason=f"{entry.get_revenue_type_display()} sin lote",
                liters=(
                    entry.quantity
                    if entry.revenue_type == RevenueEntry.RevenueType.MILK
                    else Decimal("0")
                ),
                amount=entry.gross_amount,
            )
        )

    for allocation in cost_qs.filter(group__isnull=True).select_related("animal"):
        lines.append(
            FinancialExceptionLine(
                line_type="Costo",
                occurred_on=allocation.cost_date,
                source_event_id=allocation.source_event_id,
                target=allocation.animal.tag if allocation.animal else "Hacienda",
                reason=f"{allocation.get_cost_type_display()} sin lote",
                liters=Decimal("0"),
                amount=allocation.amount,
            )
        )

    lines.sort(
        key=lambda line: (line.occurred_on, str(line.source_event_id or "")),
        reverse=True,
    )
    return lines[:limit]


DIRECT_EXPENSE_TYPES = frozenset(CostAllocation.DIRECT_EXPENSE_TYPES)


@transaction.atomic
def record_operating_expense(
    *,
    farm: Farm,
    amount: Decimal,
    cost_type: str = CostAllocation.CostType.OTHER,
    cost_date=None,
    group: HerdGroup | None = None,
    animal: Animal | None = None,
    source_event_id: UUID | None = None,
    notes: str = "",
) -> CostAllocation:
    """Book a direct operating expense that never passes through inventory.

    Labour, freight and vet fees are real cost per liter even though no input
    leaves the warehouse, so they enter the P&L through this service instead of
    being reconstructed later from accounting.
    """
    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValueError("Expense amount must be positive.")
    if cost_type not in DIRECT_EXPENSE_TYPES:
        raise ValueError(
            f"Direct expenses accept {sorted(DIRECT_EXPENSE_TYPES)}; got '{cost_type}'."
        )
    if animal and animal.farm_id != farm.id:
        raise ValueError("Animal does not belong to the farm.")
    if group and group.farm_id != farm.id:
        raise ValueError("Group does not belong to the farm.")

    return CostAllocation.objects.create(
        farm=farm,
        group=group or (animal.current_group if animal else None),
        animal=animal,
        cost_type=cost_type,
        cost_date=_normalize_date(cost_date, timezone.localdate()),
        amount=amount,
        source_event_id=source_event_id,
        notes=notes,
    )


@transaction.atomic
def record_animal_sale(
    *,
    farm: Farm,
    animal: Animal,
    amount: Decimal,
    sale_date=None,
    quantity: Decimal = Decimal("1"),
    source_event_id: UUID | None = None,
    notes: str = "",
    mark_sold: bool = True,
) -> RevenueEntry:
    """Book the sale of an animal and retire it from the productive herd."""
    amount = Decimal(str(amount))
    quantity = Decimal(str(quantity))
    if amount <= 0:
        raise ValueError("Sale amount must be positive.")
    if quantity <= 0:
        raise ValueError("Sale quantity must be positive.")
    if animal.farm_id != farm.id:
        raise ValueError("Animal does not belong to the farm.")

    entry = RevenueEntry.objects.create(
        farm=farm,
        group=animal.current_group,
        animal=animal,
        revenue_type=RevenueEntry.RevenueType.ANIMAL_SALE,
        revenue_date=_normalize_date(sale_date, timezone.localdate()),
        quantity=quantity,
        unit_price=amount / quantity,
        gross_amount=amount,
        source_event_id=source_event_id,
        notes=notes or "Venta de animal",
    )

    if mark_sold and animal.status != Animal.Status.SOLD:
        animal.status = Animal.Status.SOLD
        animal.save(update_fields=["status", "updated_at"])

    return entry


def close_operating_period(
    *,
    farm: Farm,
    group: HerdGroup | None = None,
    animal: Animal | None = None,
    start_date=None,
    end_date=None,
    notes: str = "",
) -> list[OperatingPeriodSnapshot]:
    start, end = _date_window(start_date=start_date, end_date=end_date)
    if animal:
        return [
            _upsert_snapshot(
                scope=OperatingPeriodSnapshot.Scope.ANIMAL,
                farm=farm,
                group=animal.current_group,
                animal=animal,
                start_date=start,
                end_date=end,
                pnl=get_operating_pnl(
                    farm=farm,
                    animal=animal,
                    start_date=start,
                    end_date=end,
                ),
                notes=notes,
            )
        ]

    if group:
        return [
            _upsert_snapshot(
                scope=OperatingPeriodSnapshot.Scope.GROUP,
                farm=farm,
                group=group,
                animal=None,
                start_date=start,
                end_date=end,
                pnl=get_operating_pnl(
                    farm=farm,
                    group=group,
                    start_date=start,
                    end_date=end,
                ),
                notes=notes,
            )
        ]

    snapshots = [
        _upsert_snapshot(
            scope=OperatingPeriodSnapshot.Scope.FARM,
            farm=farm,
            group=None,
            animal=None,
            start_date=start,
            end_date=end,
            pnl=get_operating_pnl(farm=farm, start_date=start, end_date=end),
            notes=notes,
        )
    ]
    for group_row in get_group_pnl(farm=farm, start_date=start, end_date=end):
        if group_row.entity_id is None:
            snapshots.append(
                _upsert_snapshot(
                    scope=OperatingPeriodSnapshot.Scope.UNASSIGNED,
                    farm=farm,
                    group=None,
                    animal=None,
                    start_date=start,
                    end_date=end,
                    pnl=group_row.pnl,
                    notes=notes,
                )
            )
            continue

        snapshots.append(
            _upsert_snapshot(
                scope=OperatingPeriodSnapshot.Scope.GROUP,
                farm=farm,
                group=HerdGroup.objects.get(id=group_row.entity_id, farm=farm),
                animal=None,
                start_date=start,
                end_date=end,
                pnl=group_row.pnl,
                notes=notes,
            )
        )
    return snapshots


def _upsert_snapshot(
    *,
    scope: str,
    farm: Farm,
    group: HerdGroup | None,
    animal: Animal | None,
    start_date: date,
    end_date: date,
    pnl: OperatingPnl,
    notes: str,
) -> OperatingPeriodSnapshot:
    identity = {
        "scope": scope,
        "farm": farm,
        "start_date": start_date,
        "end_date": end_date,
    }
    if scope == OperatingPeriodSnapshot.Scope.GROUP:
        identity["group"] = group
    if scope == OperatingPeriodSnapshot.Scope.ANIMAL:
        identity["animal"] = animal

    snapshot, _ = OperatingPeriodSnapshot.objects.update_or_create(
        **identity,
        defaults={
            "group": group,
            "animal": animal,
            "liters": pnl.liters,
            "saleable_liters": pnl.saleable_liters,
            "discarded_liters": pnl.discarded_liters,
            "discarded_value": pnl.discarded_value,
            "revenue": pnl.revenue,
            "costs": pnl.costs,
            "net_profit": pnl.net_profit,
            "cost_per_liter": pnl.cost_per_liter,
            "cost_per_saleable_liter": pnl.cost_per_saleable_liter,
            "margin_pct": pnl.margin_pct,
            "closed_at": timezone.now(),
            "notes": notes,
        },
    )
    return snapshot


def get_recent_snapshots(
    *,
    farm: Farm | None = None,
    limit: int = 8,
):
    snapshots = OperatingPeriodSnapshot.objects.select_related("farm", "group", "animal")
    if farm:
        snapshots = snapshots.filter(farm=farm)
    return snapshots.order_by("-closed_at", "-end_date")[:limit]
