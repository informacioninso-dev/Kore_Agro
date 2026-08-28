from django.db import models
from django.utils import timezone

from apps.common.models import TenantModel
from apps.herd.models import Animal, Farm, HerdGroup
from apps.inventory.models import Input


class Treatment(TenantModel):
    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="treatments")
    animal = models.ForeignKey(Animal, on_delete=models.PROTECT, related_name="treatments")
    group = models.ForeignKey(
        HerdGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="treatments",
    )
    input = models.ForeignKey(Input, null=True, blank=True, on_delete=models.SET_NULL)
    diagnosis = models.CharField(max_length=160)
    dosage = models.CharField(max_length=120, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    milk_withdrawal_until = models.DateTimeField(null=True, blank=True)
    source_event_id = models.UUIDField(null=True, blank=True, db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["started_at"]),
            models.Index(fields=["milk_withdrawal_until"]),
            models.Index(fields=["source_event_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.animal.tag} - {self.diagnosis}"


class MilkWithdrawal(TenantModel):
    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="milk_withdrawals")
    animal = models.ForeignKey(Animal, on_delete=models.PROTECT, related_name="milk_withdrawals")
    treatment = models.ForeignKey(Treatment, on_delete=models.CASCADE, related_name="withdrawals")
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()
    reason = models.CharField(max_length=160)
    source_event_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-ends_at"]
        indexes = [
            models.Index(fields=["ends_at"]),
            models.Index(fields=["source_event_id"]),
        ]

    @property
    def is_active_now(self) -> bool:
        now = timezone.now()
        return self.starts_at <= now <= self.ends_at

    def __str__(self) -> str:
        return f"{self.animal.tag} retiro hasta {self.ends_at}"

