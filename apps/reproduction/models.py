from django.db import models
from django.utils import timezone

from apps.common.models import TenantModel
from apps.herd.models import Animal, Farm, HerdGroup


class ReproductionEvent(TenantModel):
    class EventType(models.TextChoices):
        HEAT = "heat", "Celo"
        SERVICE = "service", "Inseminacion/Monta"
        PREGNANCY_CHECK = "pregnancy_check", "Chequeo prenez"
        CALVING = "calving", "Parto"
        DRY_OFF = "dry_off", "Secado"

    class ServiceType(models.TextChoices):
        AI = "ai", "Inseminacion artificial"
        NATURAL = "natural", "Monta natural"

    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="reproduction_events")
    animal = models.ForeignKey(Animal, on_delete=models.PROTECT, related_name="reproduction_events")
    group = models.ForeignKey(
        HerdGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reproduction_events",
    )
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    occurred_on = models.DateField(default=timezone.localdate)
    service_type = models.CharField(max_length=20, choices=ServiceType.choices, blank=True)
    sire_identifier = models.CharField(max_length=80, blank=True)
    pregnancy_positive = models.BooleanField(null=True, blank=True)
    calf_tag = models.CharField(max_length=40, blank=True)
    calf_sex = models.CharField(max_length=10, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    source_event_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-occurred_on", "-created_at"]
        indexes = [
            models.Index(fields=["event_type", "occurred_on"]),
            models.Index(fields=["source_event_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.animal.tag} {self.get_event_type_display()} {self.occurred_on}"

