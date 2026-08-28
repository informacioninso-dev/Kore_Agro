from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.common.models import TenantModel
from apps.herd.models import Animal, Farm, HerdGroup


class MilkingSession(TenantModel):
    class Shift(models.TextChoices):
        MORNING = "morning", "Manana"
        AFTERNOON = "afternoon", "Tarde"
        NIGHT = "night", "Noche"
        TOTAL_DAY = "total_day", "Total dia"

    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="milking_sessions")
    milking_date = models.DateField(default=timezone.localdate)
    shift = models.CharField(max_length=20, choices=Shift.choices, default=Shift.TOTAL_DAY)
    source_event_id = models.UUIDField(null=True, blank=True, db_index=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-milking_date", "shift"]
        indexes = [
            models.Index(fields=["milking_date"]),
            models.Index(fields=["source_event_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.farm.code} {self.milking_date} {self.shift}"


class MilkYield(TenantModel):
    session = models.ForeignKey(MilkingSession, on_delete=models.CASCADE, related_name="yields")
    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="milk_yields")
    group = models.ForeignKey(
        HerdGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="milk_yields",
    )
    animal = models.ForeignKey(
        Animal,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="milk_yields",
    )
    liters = models.DecimalField(max_digits=10, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0"))
    is_discarded = models.BooleanField(default=False)
    discard_reason = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["-session__milking_date", "animal__tag"]
        indexes = [
            models.Index(fields=["is_discarded"]),
        ]

    def clean(self) -> None:
        if not self.animal and not self.group:
            raise ValidationError("Milk yield requires either animal or group.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def saleable_liters(self) -> Decimal:
        return Decimal("0") if self.is_discarded else self.liters

    @property
    def gross_value(self) -> Decimal:
        return self.liters * self.unit_price

    def __str__(self) -> str:
        target = self.animal or self.group
        suffix = " (descartada)" if self.is_discarded else ""
        return f"{target}: {self.liters} L{suffix}"

