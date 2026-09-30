from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.common.models import TenantModel
from apps.herd.models import Animal, Farm, HerdGroup


class Input(TenantModel):
    class Category(models.TextChoices):
        FEED = "feed", "Balanceado"
        MEDICINE = "medicine", "Medicina"
        VACCINE = "vaccine", "Vacuna"
        SEMEN = "semen", "Semen"
        SUPPLEMENT = "supplement", "Suplemento"
        SUPPLY = "supply", "Insumo"

    class Unit(models.TextChoices):
        KG = "kg", "Kg"
        SACK = "sack", "Saco"
        DOSE = "dose", "Dosis"
        ML = "ml", "Ml"
        UNIT = "unit", "Unidad"

    name = models.CharField(max_length=160)
    sku = models.CharField(max_length=60, blank=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    unit = models.CharField(max_length=20, choices=Unit.choices)
    default_unit_cost = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0"))
    milk_withdrawal_hours = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["sku"],
                name="unique_input_sku",
                condition=~models.Q(sku=""),
            ),
        ]

    def __str__(self) -> str:
        return self.name


class StockLot(TenantModel):
    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="stock_lots")
    input = models.ForeignKey(Input, on_delete=models.PROTECT, related_name="stock_lots")
    lot_code = models.CharField(max_length=80, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    quantity_on_hand = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["input__name", "expires_on", "created_at"]

    def __str__(self) -> str:
        suffix = f" {self.lot_code}" if self.lot_code else ""
        return f"{self.input.name}{suffix}"


class InventoryMovement(TenantModel):
    class MovementType(models.TextChoices):
        IN = "in", "Ingreso"
        OUT = "out", "Consumo"
        ADJUSTMENT = "adjustment", "Ajuste"
        RETURN = "return", "Devolucion a proveedor"

    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="inventory_movements")
    input = models.ForeignKey(Input, on_delete=models.PROTECT, related_name="movements")
    stock_lot = models.ForeignKey(
        StockLot,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="movements",
    )
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4)
    total_cost = models.DecimalField(max_digits=14, decimal_places=4)
    occurred_at = models.DateTimeField(default=timezone.now)
    animal = models.ForeignKey(
        Animal,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inventory_movements",
    )
    group = models.ForeignKey(
        HerdGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inventory_movements",
    )
    source_event_id = models.UUIDField(null=True, blank=True, db_index=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-occurred_at", "-created_at"]
        indexes = [
            models.Index(fields=["occurred_at"]),
            models.Index(fields=["source_event_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_movement_type_display()} {self.quantity} {self.input.unit}"
