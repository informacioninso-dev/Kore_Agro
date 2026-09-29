from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.common.models import TenantModel
from apps.herd.models import Animal, Farm, HerdGroup


class WeightRecord(TenantModel):
    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="weight_records")
    animal = models.ForeignKey(Animal, on_delete=models.PROTECT, related_name="weight_records")
    group = models.ForeignKey(
        HerdGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="weight_records",
    )
    weighed_on = models.DateField(default=timezone.localdate)
    weight_kg = models.DecimalField(max_digits=8, decimal_places=2)
    body_condition_score = models.DecimalField(
        max_digits=2,
        decimal_places=1,
        null=True,
        blank=True,
    )
    scale_identifier = models.CharField(max_length=120, blank=True)
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="weight_records",
    )
    source_event_id = models.UUIDField(null=True, blank=True, db_index=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-weighed_on", "-created_at"]
        indexes = [
            models.Index(fields=["animal", "weighed_on"]),
            models.Index(fields=["group", "weighed_on"]),
            models.Index(fields=["source_event_id"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(weight_kg__gt=0),
                name="positive_weight_record_kg",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(body_condition_score__isnull=True)
                    | models.Q(body_condition_score__gte=1, body_condition_score__lte=5)
                ),
                name="valid_weight_body_condition_score",
            ),
        ]

    def clean(self) -> None:
        errors = {}
        if self.animal_id and self.farm_id and self.animal.farm_id != self.farm_id:
            errors["animal"] = "El animal no pertenece a la hacienda seleccionada."
        if self.group_id and self.farm_id and self.group.farm_id != self.farm_id:
            errors["group"] = "El lote no pertenece a la hacienda seleccionada."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.animal.tag}: {self.weight_kg} kg ({self.weighed_on})"
