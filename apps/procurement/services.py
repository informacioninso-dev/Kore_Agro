from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.inventory.services import receive_input

from .models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine


@dataclass(frozen=True)
class PurchaseReceiptResult:
    receipt: GoodsReceipt
    line: GoodsReceiptLine


@transaction.atomic
def add_purchase_line(
    *,
    purchase_order: PurchaseOrder,
    input_,
    quantity: Decimal,
    unit_cost: Decimal,
    tax_rate: Decimal = Decimal("0"),
) -> PurchaseOrderLine:
    order = PurchaseOrder.objects.select_for_update().get(pk=purchase_order.pk)
    if order.status != PurchaseOrder.Status.DRAFT:
        raise ValidationError("Solo se pueden modificar ordenes en borrador.")
    return PurchaseOrderLine.objects.create(
        purchase_order=order,
        input=input_,
        quantity_ordered=quantity,
        unit_cost=unit_cost,
        tax_rate=tax_rate,
    )


@transaction.atomic
def place_purchase_order(purchase_order: PurchaseOrder) -> PurchaseOrder:
    order = PurchaseOrder.objects.select_for_update().get(pk=purchase_order.pk)
    if order.status != PurchaseOrder.Status.DRAFT:
        raise ValidationError("La orden ya no esta en borrador.")
    if not order.lines.exists():
        raise ValidationError("Agrega al menos un insumo antes de emitir la orden.")
    order.status = PurchaseOrder.Status.ORDERED
    order.save(update_fields=["status", "updated_at"])
    return order


@transaction.atomic
def cancel_purchase_order(purchase_order: PurchaseOrder) -> PurchaseOrder:
    order = PurchaseOrder.objects.select_for_update().get(pk=purchase_order.pk)
    if order.status == PurchaseOrder.Status.RECEIVED or order.receipts.exists():
        raise ValidationError("Una orden con recepciones no puede cancelarse.")
    if order.status == PurchaseOrder.Status.CANCELLED:
        raise ValidationError("La orden ya esta cancelada.")
    order.status = PurchaseOrder.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    return order


@transaction.atomic
def receive_purchase_line(
    *,
    order_line: PurchaseOrderLine,
    quantity: Decimal,
    received_at: datetime | None = None,
    lot_code: str = "",
    expires_on=None,
    supplier_document: str = "",
    source_event_id: UUID | None = None,
    notes: str = "",
) -> PurchaseReceiptResult:
    line = (
        PurchaseOrderLine.objects.select_for_update()
        .select_related("purchase_order__farm", "purchase_order__supplier", "input")
        .get(pk=order_line.pk)
    )
    order = line.purchase_order
    if order.status not in {PurchaseOrder.Status.ORDERED, PurchaseOrder.Status.PARTIAL}:
        raise ValidationError("La orden debe estar emitida para recibirla.")

    received_quantity = Decimal(str(quantity))
    if received_quantity <= 0:
        raise ValidationError("La cantidad recibida debe ser mayor que cero.")
    if received_quantity > line.remaining_quantity:
        raise ValidationError(
            f"La cantidad supera el saldo pendiente de {line.remaining_quantity} {line.input.unit}."
        )

    effective_received_at = received_at or timezone.now()
    inventory_result = receive_input(
        farm=order.farm,
        input_=line.input,
        quantity=received_quantity,
        unit_cost=line.unit_cost,
        occurred_at=effective_received_at,
        lot_code=lot_code,
        expires_on=expires_on,
        source_event_id=source_event_id,
        notes=notes or f"Compra {order.number} - {order.supplier.display_name}",
    )
    receipt = GoodsReceipt.objects.create(
        purchase_order=order,
        received_at=effective_received_at,
        supplier_document=supplier_document,
        source_event_id=source_event_id,
        notes=notes,
    )
    receipt_line = GoodsReceiptLine.objects.create(
        receipt=receipt,
        order_line=line,
        quantity=received_quantity,
        unit_cost=line.unit_cost,
        lot_code=lot_code,
        expires_on=expires_on,
        inventory_movement_id=inventory_result.movement_id,
    )
    line.quantity_received += received_quantity
    line.save(update_fields=["quantity_received", "updated_at"])

    has_pending = PurchaseOrderLine.objects.filter(purchase_order=order).exclude(
        quantity_received__gte=models.F("quantity_ordered")
    ).exists()
    order.status = PurchaseOrder.Status.PARTIAL if has_pending else PurchaseOrder.Status.RECEIVED
    order.save(update_fields=["status", "updated_at"])
    return PurchaseReceiptResult(receipt=receipt, line=receipt_line)
