from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.finance.models import CostAllocation
from apps.herd.models import Animal, Farm, HerdGroup

from .models import Input, InventoryMovement, StockLot


class InsufficientStockError(ValueError):
    pass


@dataclass(frozen=True)
class ConsumptionResult:
    movement_ids: list[UUID]
    total_cost: Decimal


@dataclass(frozen=True)
class ReceiptResult:
    stock_lot_id: UUID
    movement_id: UUID
    quantity: Decimal
    unit_cost: Decimal
    total_cost: Decimal


@dataclass(frozen=True)
class AdjustmentResult:
    movement_ids: list[UUID]
    quantity_delta: Decimal
    recognized_cost: Decimal


def cost_type_for_input(input_: Input) -> str:
    mapping = {
        Input.Category.FEED: CostAllocation.CostType.FEED,
        Input.Category.MEDICINE: CostAllocation.CostType.MEDICINE,
        Input.Category.VACCINE: CostAllocation.CostType.VACCINE,
        Input.Category.SEMEN: CostAllocation.CostType.SEMEN,
        Input.Category.SUPPLEMENT: CostAllocation.CostType.SUPPLEMENT,
        Input.Category.SUPPLY: CostAllocation.CostType.SUPPLY,
    }
    return mapping.get(input_.category, CostAllocation.CostType.OTHER)


def _draw_fifo(*, farm: Farm, input_: Input, quantity: Decimal) -> list[tuple[StockLot, Decimal]]:
    """Take `quantity` from stock, oldest expiry first, updating each lot."""
    remaining = quantity
    draws: list[tuple[StockLot, Decimal]] = []

    stock_lots = (
        StockLot.objects.select_for_update()
        .filter(farm=farm, input=input_, quantity_on_hand__gt=0)
        .order_by("expires_on", "created_at")
    )

    for stock_lot in stock_lots:
        if remaining <= 0:
            break
        used = min(stock_lot.quantity_on_hand, remaining)
        stock_lot.quantity_on_hand -= used
        stock_lot.save(update_fields=["quantity_on_hand", "updated_at"])
        draws.append((stock_lot, used))
        remaining -= used

    if remaining > 0:
        raise InsufficientStockError(
            f"Stock insuficiente para {input_.name}: requerido {quantity}, faltante {remaining}."
        )
    return draws


@transaction.atomic
def consume_input(
    *,
    farm: Farm,
    input_: Input,
    quantity: Decimal,
    occurred_at,
    source_event_id: UUID | None = None,
    animal: Animal | None = None,
    group: HerdGroup | None = None,
    notes: str = "",
) -> ConsumptionResult:
    if quantity <= 0:
        raise ValueError("Consumption quantity must be positive.")

    cost_date = timezone.localtime(occurred_at).date()
    movement_ids: list[UUID] = []
    total_cost = Decimal("0")

    for stock_lot, used in _draw_fifo(farm=farm, input_=input_, quantity=quantity):
        line_total = used * stock_lot.unit_cost
        movement = InventoryMovement.objects.create(
            farm=farm,
            input=input_,
            stock_lot=stock_lot,
            movement_type=InventoryMovement.MovementType.OUT,
            quantity=used,
            unit_cost=stock_lot.unit_cost,
            total_cost=line_total,
            occurred_at=occurred_at,
            animal=animal,
            group=group,
            source_event_id=source_event_id,
            notes=notes,
        )
        CostAllocation.objects.create(
            farm=farm,
            group=group,
            animal=animal,
            cost_type=cost_type_for_input(input_),
            cost_date=cost_date,
            amount=line_total,
            source_event_id=source_event_id,
            inventory_movement_id=movement.id,
            notes=notes or input_.name,
        )
        movement_ids.append(movement.id)
        total_cost += line_total

    return ConsumptionResult(movement_ids=movement_ids, total_cost=total_cost)


@transaction.atomic
def receive_input(
    *,
    farm: Farm,
    input_: Input,
    quantity: Decimal,
    unit_cost: Decimal | None = None,
    occurred_at=None,
    lot_code: str = "",
    expires_on=None,
    source_event_id: UUID | None = None,
    notes: str = "",
) -> ReceiptResult:
    """Register a purchase/reception of an input.

    A reception moves money into inventory, not into the P&L: the cost is
    recognized when the input is consumed, which is what keeps cost per liter
    honest. Receiving into an existing lot re-weights its unit cost.
    """
    if quantity <= 0:
        raise ValueError("Receipt quantity must be positive.")

    occurred_at = occurred_at or timezone.now()
    cost = unit_cost if unit_cost is not None else input_.default_unit_cost
    if cost < 0:
        raise ValueError("Receipt unit cost cannot be negative.")

    stock_lot = (
        StockLot.objects.select_for_update()
        .filter(farm=farm, input=input_, lot_code=lot_code, expires_on=expires_on)
        .order_by("created_at")
        .first()
    )

    if stock_lot is None:
        stock_lot = StockLot.objects.create(
            farm=farm,
            input=input_,
            lot_code=lot_code,
            expires_on=expires_on,
            quantity_on_hand=quantity,
            unit_cost=cost,
        )
    else:
        stock_lot.unit_cost = _weighted_unit_cost(
            current_quantity=stock_lot.quantity_on_hand,
            current_cost=stock_lot.unit_cost,
            incoming_quantity=quantity,
            incoming_cost=cost,
        )
        stock_lot.quantity_on_hand += quantity
        stock_lot.is_active = True
        stock_lot.save(update_fields=["quantity_on_hand", "unit_cost", "is_active", "updated_at"])

    movement = InventoryMovement.objects.create(
        farm=farm,
        input=input_,
        stock_lot=stock_lot,
        movement_type=InventoryMovement.MovementType.IN,
        quantity=quantity,
        unit_cost=cost,
        total_cost=quantity * cost,
        occurred_at=occurred_at,
        source_event_id=source_event_id,
        notes=notes,
    )

    return ReceiptResult(
        stock_lot_id=stock_lot.id,
        movement_id=movement.id,
        quantity=quantity,
        unit_cost=cost,
        total_cost=quantity * cost,
    )


def _weighted_unit_cost(
    *,
    current_quantity: Decimal,
    current_cost: Decimal,
    incoming_quantity: Decimal,
    incoming_cost: Decimal,
) -> Decimal:
    if current_quantity <= 0:
        return incoming_cost
    total_quantity = current_quantity + incoming_quantity
    value = current_quantity * current_cost + incoming_quantity * incoming_cost
    return value / total_quantity


@transaction.atomic
def adjust_stock(
    *,
    farm: Farm,
    input_: Input,
    quantity_delta: Decimal,
    occurred_at=None,
    reason: str = "",
    stock_lot: StockLot | None = None,
    animal: Animal | None = None,
    group: HerdGroup | None = None,
    source_event_id: UUID | None = None,
) -> AdjustmentResult:
    """Correct stock against a physical count.

    Shortfalls are real money lost, so they are recognized as a `shrinkage`
    cost. Surpluses only restore inventory; their cost reaches the P&L when
    consumed, exactly like a reception.
    """
    if quantity_delta == 0:
        raise ValueError("Adjustment delta cannot be zero.")

    occurred_at = occurred_at or timezone.now()
    cost_date = timezone.localtime(occurred_at).date()
    notes = reason or "Ajuste de inventario"

    if quantity_delta > 0:
        movement = _adjust_up(
            farm=farm,
            input_=input_,
            quantity=quantity_delta,
            occurred_at=occurred_at,
            stock_lot=stock_lot,
            animal=animal,
            group=group,
            source_event_id=source_event_id,
            notes=notes,
        )
        return AdjustmentResult(
            movement_ids=[movement.id],
            quantity_delta=quantity_delta,
            recognized_cost=Decimal("0"),
        )

    shortfall = -quantity_delta
    movement_ids: list[UUID] = []
    recognized_cost = Decimal("0")

    for drawn_lot, used in _draw_fifo(farm=farm, input_=input_, quantity=shortfall):
        line_total = used * drawn_lot.unit_cost
        movement = InventoryMovement.objects.create(
            farm=farm,
            input=input_,
            stock_lot=drawn_lot,
            movement_type=InventoryMovement.MovementType.ADJUSTMENT,
            quantity=-used,
            unit_cost=drawn_lot.unit_cost,
            total_cost=-line_total,
            occurred_at=occurred_at,
            animal=animal,
            group=group,
            source_event_id=source_event_id,
            notes=notes,
        )
        CostAllocation.objects.create(
            farm=farm,
            group=group,
            animal=animal,
            cost_type=CostAllocation.CostType.SHRINKAGE,
            cost_date=cost_date,
            amount=line_total,
            source_event_id=source_event_id,
            inventory_movement_id=movement.id,
            notes=notes,
        )
        movement_ids.append(movement.id)
        recognized_cost += line_total

    return AdjustmentResult(
        movement_ids=movement_ids,
        quantity_delta=quantity_delta,
        recognized_cost=recognized_cost,
    )


def _adjust_up(
    *,
    farm: Farm,
    input_: Input,
    quantity: Decimal,
    occurred_at,
    stock_lot: StockLot | None,
    animal: Animal | None,
    group: HerdGroup | None,
    source_event_id: UUID | None,
    notes: str,
) -> InventoryMovement:
    target = stock_lot or (
        StockLot.objects.select_for_update()
        .filter(farm=farm, input=input_, is_active=True)
        .order_by("expires_on", "created_at")
        .first()
    )
    if target is None:
        target = StockLot.objects.create(
            farm=farm,
            input=input_,
            lot_code="AJUSTE",
            quantity_on_hand=Decimal("0"),
            unit_cost=input_.default_unit_cost,
        )

    target.quantity_on_hand += quantity
    target.save(update_fields=["quantity_on_hand", "updated_at"])

    return InventoryMovement.objects.create(
        farm=farm,
        input=input_,
        stock_lot=target,
        movement_type=InventoryMovement.MovementType.ADJUSTMENT,
        quantity=quantity,
        unit_cost=target.unit_cost,
        total_cost=quantity * target.unit_cost,
        occurred_at=occurred_at,
        animal=animal,
        group=group,
        source_event_id=source_event_id,
        notes=notes,
    )
