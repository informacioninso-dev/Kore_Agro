from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.inventory.models import InventoryMovement
from apps.inventory.services import receive_input

from .models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseInvoice,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchasePayment,
    PurchaseReturn,
)


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
def submit_purchase_order(purchase_order: PurchaseOrder, *, user=None) -> PurchaseOrder:
    order = PurchaseOrder.objects.select_for_update().get(pk=purchase_order.pk)
    if order.status != PurchaseOrder.Status.DRAFT:
        raise ValidationError("La orden ya no esta en borrador.")
    if not order.lines.exists():
        raise ValidationError("Agrega al menos un insumo antes de enviar la orden.")
    order.status = PurchaseOrder.Status.PENDING_APPROVAL
    order.submitted_at = timezone.now()
    order.submitted_by = user
    order.save(update_fields=["status", "submitted_at", "submitted_by", "updated_at"])
    return order


@transaction.atomic
def approve_purchase_order(purchase_order: PurchaseOrder, *, user=None) -> PurchaseOrder:
    order = PurchaseOrder.objects.select_for_update().get(pk=purchase_order.pk)
    if order.status != PurchaseOrder.Status.PENDING_APPROVAL:
        raise ValidationError("La orden no esta pendiente de aprobacion.")
    order.status = PurchaseOrder.Status.ORDERED
    order.approved_at = timezone.now()
    order.approved_by = user
    order.rejected_at = None
    order.rejected_by = None
    order.rejection_reason = ""
    order.save(
        update_fields=[
            "status",
            "approved_at",
            "approved_by",
            "rejected_at",
            "rejected_by",
            "rejection_reason",
            "updated_at",
        ]
    )
    return order


@transaction.atomic
def reject_purchase_order(
    purchase_order: PurchaseOrder,
    *,
    user=None,
    reason: str,
) -> PurchaseOrder:
    order = PurchaseOrder.objects.select_for_update().get(pk=purchase_order.pk)
    if order.status != PurchaseOrder.Status.PENDING_APPROVAL:
        raise ValidationError("La orden no esta pendiente de aprobacion.")
    if not reason.strip():
        raise ValidationError("Indica el motivo del rechazo.")
    order.status = PurchaseOrder.Status.REJECTED
    order.rejected_at = timezone.now()
    order.rejected_by = user
    order.rejection_reason = reason.strip()
    order.save(
        update_fields=[
            "status",
            "rejected_at",
            "rejected_by",
            "rejection_reason",
            "updated_at",
        ]
    )
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


@transaction.atomic
def record_purchase_invoice(
    *,
    purchase_order: PurchaseOrder,
    invoice_number: str,
    issued_on,
    due_on,
    user=None,
    notes: str = "",
) -> PurchaseInvoice:
    order = (
        PurchaseOrder.objects.select_for_update()
        .select_related("supplier")
        .prefetch_related("lines", "receipts__lines__returns")
        .get(pk=purchase_order.pk)
    )
    if order.status != PurchaseOrder.Status.RECEIVED:
        raise ValidationError("La orden debe estar recibida antes de registrar su factura.")
    if PurchaseInvoice.objects.filter(purchase_order=order).exists():
        raise ValidationError("La orden ya tiene una factura registrada.")
    if not invoice_number.strip():
        raise ValidationError("Indica el numero de factura.")

    credit_amount = sum(
        (
            purchase_return.credit_amount
            for receipt in order.receipts.all()
            for receipt_line in receipt.lines.all()
            for purchase_return in receipt_line.returns.all()
        ),
        Decimal("0"),
    )
    return PurchaseInvoice.objects.create(
        purchase_order=order,
        invoice_number=invoice_number.strip(),
        issued_on=issued_on,
        due_on=due_on,
        subtotal=order.subtotal,
        tax_amount=order.tax_amount,
        total_amount=order.total_amount,
        credit_amount=credit_amount,
        recorded_by=user,
        notes=notes,
    )


@transaction.atomic
def record_purchase_payment(
    *,
    invoice: PurchaseInvoice,
    amount: Decimal,
    paid_on,
    method: str,
    reference: str = "",
    notes: str = "",
    user=None,
) -> PurchasePayment:
    locked_invoice = PurchaseInvoice.objects.select_for_update().get(pk=invoice.pk)
    payment_amount = Decimal(str(amount))
    if locked_invoice.status == PurchaseInvoice.Status.CANCELLED:
        raise ValidationError("La factura esta anulada.")
    if payment_amount <= 0:
        raise ValidationError("El pago debe ser mayor que cero.")
    if payment_amount > locked_invoice.balance_due:
        raise ValidationError(f"El pago supera el saldo de {locked_invoice.balance_due}.")
    if method not in PurchasePayment.Method.values:
        raise ValidationError("Selecciona una forma de pago valida.")

    payment = PurchasePayment.objects.create(
        invoice=locked_invoice,
        paid_on=paid_on,
        amount=payment_amount,
        method=method,
        reference=reference,
        notes=notes,
        recorded_by=user,
    )
    remaining = locked_invoice.balance_due
    locked_invoice.status = (
        PurchaseInvoice.Status.PAID if remaining == 0 else PurchaseInvoice.Status.PARTIAL
    )
    locked_invoice.save(update_fields=["status", "updated_at"])
    return payment


@transaction.atomic
def return_purchase_receipt(
    *,
    receipt_line: GoodsReceiptLine,
    quantity: Decimal,
    reason: str,
    returned_at: datetime | None = None,
    credit_document: str = "",
    user=None,
) -> PurchaseReturn:
    line = (
        GoodsReceiptLine.objects.select_for_update(of=("self",))
        .select_related(
            "receipt__purchase_order__farm",
            "order_line__input",
            "inventory_movement__stock_lot",
        )
        .get(pk=receipt_line.pk)
    )
    return_quantity = Decimal(str(quantity))
    already_returned = line.returns.aggregate(total=models.Sum("quantity"))["total"] or Decimal(
        "0"
    )
    if return_quantity <= 0:
        raise ValidationError("La cantidad devuelta debe ser mayor que cero.")
    if return_quantity > line.quantity - already_returned:
        raise ValidationError("La devolucion supera la cantidad recibida disponible.")
    if not reason.strip():
        raise ValidationError("Indica el motivo de la devolucion.")

    stock_lot = line.inventory_movement.stock_lot
    if not stock_lot:
        raise ValidationError("La recepcion no tiene un lote de inventario asociado.")
    stock_lot = stock_lot.__class__.objects.select_for_update().get(pk=stock_lot.pk)
    if stock_lot.quantity_on_hand < return_quantity:
        raise ValidationError("No existe stock suficiente del lote recibido para devolverlo.")
    stock_lot.quantity_on_hand -= return_quantity
    stock_lot.save(update_fields=["quantity_on_hand", "updated_at"])

    effective_returned_at = returned_at or timezone.now()
    movement = InventoryMovement.objects.create(
        farm=line.receipt.purchase_order.farm,
        input=line.order_line.input,
        stock_lot=stock_lot,
        movement_type=InventoryMovement.MovementType.RETURN,
        quantity=-return_quantity,
        unit_cost=line.unit_cost,
        total_cost=-(return_quantity * line.unit_cost),
        occurred_at=effective_returned_at,
        notes=f"Devolucion {line.receipt.purchase_order.number}: {reason.strip()}",
    )
    purchase_return = PurchaseReturn.objects.create(
        receipt_line=line,
        returned_at=effective_returned_at,
        quantity=return_quantity,
        unit_cost=line.unit_cost,
        reason=reason.strip(),
        credit_document=credit_document,
        inventory_movement=movement,
        recorded_by=user,
    )

    invoice = PurchaseInvoice.objects.select_for_update().filter(
        purchase_order=line.receipt.purchase_order
    ).first()
    if invoice:
        invoice.credit_amount += purchase_return.credit_amount
        invoice.credit_amount = min(invoice.credit_amount, invoice.total_amount)
        if invoice.balance_due == 0:
            invoice.status = PurchaseInvoice.Status.PAID
        elif invoice.amount_paid:
            invoice.status = PurchaseInvoice.Status.PARTIAL
        else:
            invoice.status = PurchaseInvoice.Status.PENDING
        invoice.save(update_fields=["credit_amount", "status", "updated_at"])
    return purchase_return
