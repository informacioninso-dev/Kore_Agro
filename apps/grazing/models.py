from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.common.models import SoftDeleteModel, TenantModel
from apps.herd.models import Farm, HerdGroup


class Paddock(TenantModel, SoftDeleteModel):
    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="paddocks")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40)
    area_hectares = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    forage_type = models.CharField(max_length=120, blank=True)
    rest_target_days = models.PositiveSmallIntegerField(
        default=21,
        validators=[MinValueValidator(1)],
    )
    capacity_animals = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["farm__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "name"],
                name="unique_paddock_name_per_farm",
            ),
            models.UniqueConstraint(
                fields=["farm", "code"],
                name="unique_paddock_code_per_farm",
            ),
            models.CheckConstraint(
                condition=models.Q(area_hectares__gt=0),
                name="positive_paddock_area",
            ),
            models.CheckConstraint(
                condition=models.Q(rest_target_days__gt=0),
                name="positive_paddock_rest_target",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.farm.code} - {self.name}"


class GrazingPeriod(TenantModel):
    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="grazing_periods")
    paddock = models.ForeignKey(
        Paddock,
        on_delete=models.PROTECT,
        related_name="grazing_periods",
    )
    group = models.ForeignKey(
        HerdGroup,
        on_delete=models.PROTECT,
        related_name="grazing_periods",
    )
    started_on = models.DateField(default=timezone.localdate)
    planned_end_on = models.DateField(null=True, blank=True)
    ended_on = models.DateField(null=True, blank=True)
    head_count = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    entry_biomass_kg_ha = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    exit_biomass_kg_ha = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    source_event_id = models.UUIDField(null=True, blank=True, db_index=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-started_on", "-created_at"]
        indexes = [
            models.Index(fields=["farm", "started_on"]),
            models.Index(fields=["paddock", "started_on"]),
            models.Index(fields=["group", "started_on"]),
            models.Index(fields=["source_event_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["paddock"],
                condition=models.Q(ended_on__isnull=True),
                name="one_active_period_per_paddock",
            ),
            models.UniqueConstraint(
                fields=["group"],
                condition=models.Q(ended_on__isnull=True),
                name="one_active_period_per_group",
            ),
            models.CheckConstraint(
                condition=models.Q(ended_on__isnull=True)
                | models.Q(ended_on__gte=models.F("started_on")),
                name="grazing_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(planned_end_on__isnull=True)
                | models.Q(planned_end_on__gte=models.F("started_on")),
                name="grazing_planned_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(head_count__gt=0),
                name="positive_grazing_head_count",
            ),
        ]

    def clean(self) -> None:
        errors = {}
        if self.paddock_id and self.farm_id and self.paddock.farm_id != self.farm_id:
            errors["paddock"] = "El potrero no pertenece a la hacienda seleccionada."
        if self.group_id and self.farm_id and self.group.farm_id != self.farm_id:
            errors["group"] = "El lote no pertenece a la hacienda seleccionada."
        if self.ended_on and self.ended_on < self.started_on:
            errors["ended_on"] = "La salida no puede ser anterior a la entrada."
        if self.planned_end_on and self.planned_end_on < self.started_on:
            errors["planned_end_on"] = "La salida prevista no puede ser anterior a la entrada."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_active(self) -> bool:
        return self.ended_on is None

    @property
    def occupied_days(self) -> int:
        end = self.ended_on or timezone.localdate()
        return max((end - self.started_on).days + 1, 0)

    def __str__(self) -> str:
        return f"{self.group.name} en {self.paddock.name} desde {self.started_on}"
