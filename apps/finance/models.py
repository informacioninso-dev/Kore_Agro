from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.common.models import TenantModel
from apps.herd.models import Animal, Farm, HerdGroup


class RevenueEntry(TenantModel):
    class RevenueType(models.TextChoices):
        MILK = "milk", "Leche"
        ANIMAL_SALE = "animal_sale", "Venta animal"
        OTHER = "other", "Otro"

    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="revenue_entries")
    group = models.ForeignKey(
        HerdGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revenue_entries",
    )
    animal = models.ForeignKey(
        Animal,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revenue_entries",
    )
    revenue_type = models.CharField(max_length=30, choices=RevenueType.choices)
    revenue_date = models.DateField(default=timezone.localdate)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    unit_price = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0"))
    gross_amount = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0"))
    source_event_id = models.UUIDField(null=True, blank=True, db_index=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-revenue_date", "-created_at"]
        indexes = [
            models.Index(fields=["revenue_date"]),
            models.Index(fields=["source_event_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_revenue_type_display()} {self.gross_amount}"


class CostAllocation(TenantModel):
    class CostType(models.TextChoices):
        FEED = "feed", "Balanceado"
        MEDICINE = "medicine", "Medicina"
        VACCINE = "vaccine", "Vacuna"
        SEMEN = "semen", "Semen"
        SUPPLEMENT = "supplement", "Suplemento"
        SUPPLY = "supply", "Insumo"
        LABOR = "labor", "Mano de obra"
        SERVICE = "service", "Servicios"
        SHRINKAGE = "shrinkage", "Merma"
        OTHER = "other", "Otro"

    DIRECT_EXPENSE_TYPES = ("labor", "service", "supply", "other")

    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="cost_allocations")
    group = models.ForeignKey(
        HerdGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cost_allocations",
    )
    animal = models.ForeignKey(
        Animal,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cost_allocations",
    )
    cost_type = models.CharField(max_length=30, choices=CostType.choices)
    cost_date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=14, decimal_places=4)
    source_event_id = models.UUIDField(null=True, blank=True, db_index=True)
    inventory_movement_id = models.UUIDField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-cost_date", "-created_at"]
        indexes = [
            models.Index(fields=["cost_date"]),
            models.Index(fields=["source_event_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_cost_type_display()} {self.amount}"


class OperatingPeriodSnapshot(TenantModel):
    class Scope(models.TextChoices):
        FARM = "farm", "Hacienda"
        GROUP = "group", "Lote"
        ANIMAL = "animal", "Animal"
        UNASSIGNED = "unassigned", "Sin asignar"

    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="pnl_snapshots")
    group = models.ForeignKey(
        HerdGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pnl_snapshots",
    )
    animal = models.ForeignKey(
        Animal,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pnl_snapshots",
    )
    scope = models.CharField(max_length=20, choices=Scope.choices)
    start_date = models.DateField()
    end_date = models.DateField()
    liters = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    saleable_liters = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    discarded_liters = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    discarded_value = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal("0"))
    revenue = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal("0"))
    costs = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal("0"))
    net_profit = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal("0"))
    cost_per_liter = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal("0"))
    cost_per_saleable_liter = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        default=Decimal("0"),
    )
    margin_pct = models.DecimalField(max_digits=9, decimal_places=4, default=Decimal("0"))
    closed_at = models.DateTimeField(default=timezone.now)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-end_date", "scope", "farm__name"]
        indexes = [
            models.Index(fields=["farm", "start_date", "end_date"]),
            models.Index(fields=["scope", "end_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(start_date__lte=models.F("end_date")),
                name="valid_operating_snapshot_window",
            ),
            models.UniqueConstraint(
                fields=["farm", "start_date", "end_date"],
                condition=models.Q(scope="farm"),
                name="unique_farm_period_snapshot",
            ),
            models.UniqueConstraint(
                fields=["farm", "group", "start_date", "end_date"],
                condition=models.Q(scope="group", group__isnull=False),
                name="unique_group_period_snapshot",
            ),
            models.UniqueConstraint(
                fields=["farm", "animal", "start_date", "end_date"],
                condition=models.Q(scope="animal", animal__isnull=False),
                name="unique_animal_period_snapshot",
            ),
            models.UniqueConstraint(
                fields=["farm", "start_date", "end_date"],
                condition=models.Q(scope="unassigned"),
                name="unique_unassigned_period_snapshot",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_scope_display()} {self.start_date} - {self.end_date}"
