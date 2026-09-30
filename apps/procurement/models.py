from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.common.models import TenantModel
from apps.herd.models import Farm
from apps.inventory.models import Input, InventoryMovement
from apps.parties.models import Counterparty


class PurchaseOrder(TenantModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        ORDERED = "ordered", "Ordenada"
        PARTIAL = "partial", "Recibida parcialmente"
        RECEIVED = "received", "Recibida"
        CANCELLED = "cancelled", "Cancelada"

    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="purchase_orders")
    supplier = models.ForeignKey(
        Counterparty,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    number = models.CharField(max_length=40, unique=True)
    ordered_on = models.DateField(default=timezone.localdate)
    expected_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-ordered_on", "-created_at"]
        indexes = [models.Index(fields=["farm", "status", "ordered_on"])]

    def clean(self) -> None:
        errors = {}
        if self.supplier_id and (not self.supplier.is_active or not self.supplier.is_supplier):
            errors["supplier"] = "Selecciona un proveedor activo."
        if self.expected_on and self.expected_on < self.ordered_on:
            errors["expected_on"] = "La entrega esperada no puede ser anterior a la orden."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def subtotal(self) -> Decimal:
        return sum((line.subtotal for line in self.lines.all()), Decimal("0"))

    @property
    def tax_amount(self) -> Decimal:
        return sum((line.tax_amount for line in self.lines.all()), Decimal("0"))

    @property
    def total_amount(self) -> Decimal:
        return self.subtotal + self.tax_amount

    @property
    def received_amount(self) -> Decimal:
        return sum((line.received_amount for line in self.lines.all()), Decimal("0"))

    def __str__(self) -> str:
        return f"{self.number} - {self.supplier.display_name}"


class PurchaseOrderLine(TenantModel):
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    input = models.ForeignKey(Input, on_delete=models.PROTECT, related_name="purchase_lines")
    quantity_ordered = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0"))],
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    quantity_received = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity_ordered__gt=0),
                name="positive_purchase_order_quantity",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_cost__gte=0),
                name="nonnegative_purchase_unit_cost",
            ),
            models.CheckConstraint(
                condition=models.Q(tax_rate__gte=0) & models.Q(tax_rate__lte=100),
                name="valid_purchase_tax_rate",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity_received__gte=0)
                & models.Q(quantity_received__lte=models.F("quantity_ordered")),
                name="valid_received_purchase_quantity",
            ),
        ]

    def clean(self) -> None:
        if self.input_id and not self.input.is_active:
            raise ValidationError({"input": "El insumo seleccionado esta inactivo."})
        if self.quantity_received > self.quantity_ordered:
            raise ValidationError({"quantity_received": "La recepcion supera lo ordenado."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def remaining_quantity(self) -> Decimal:
        return self.quantity_ordered - self.quantity_received

    @property
    def subtotal(self) -> Decimal:
        return self.quantity_ordered * self.unit_cost

    @property
    def tax_amount(self) -> Decimal:
        return self.subtotal * self.tax_rate / Decimal("100")

    @property
    def total_amount(self) -> Decimal:
        return self.subtotal + self.tax_amount

    @property
    def received_amount(self) -> Decimal:
        return self.quantity_received * self.unit_cost

    def __str__(self) -> str:
        return f"{self.purchase_order.number} - {self.input.name}"


class GoodsReceipt(TenantModel):
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT,
        related_name="receipts",
    )
    received_at = models.DateTimeField(default=timezone.now)
    supplier_document = models.CharField(max_length=80, blank=True)
    source_event_id = models.UUIDField(null=True, blank=True, db_index=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-received_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_event_id"],
                condition=models.Q(source_event_id__isnull=False),
                name="unique_goods_receipt_source_event",
            )
        ]

    @property
    def total_amount(self) -> Decimal:
        return sum((line.total_amount for line in self.lines.all()), Decimal("0"))

    def __str__(self) -> str:
        return f"Recepcion {self.purchase_order.number} - {self.received_at:%Y-%m-%d}"


class GoodsReceiptLine(TenantModel):
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="lines")
    order_line = models.ForeignKey(
        PurchaseOrderLine,
        on_delete=models.PROTECT,
        related_name="receipt_lines",
    )
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0"))],
    )
    lot_code = models.CharField(max_length=80, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    inventory_movement = models.OneToOneField(
        InventoryMovement,
        on_delete=models.PROTECT,
        related_name="purchase_receipt_line",
    )

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="positive_goods_receipt_quantity",
            )
        ]

    def clean(self) -> None:
        if (
            self.receipt_id
            and self.order_line_id
            and self.receipt.purchase_order_id != self.order_line.purchase_order_id
        ):
            raise ValidationError("La linea no pertenece a la orden recibida.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def total_amount(self) -> Decimal:
        return self.quantity * self.unit_cost

    def __str__(self) -> str:
        return f"{self.order_line.input.name}: {self.quantity}"
