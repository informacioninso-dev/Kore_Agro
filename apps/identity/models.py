from django.conf import settings
from django.db import models

from apps.common.models import TenantModel


class FieldDevice(TenantModel):
    name = models.CharField(max_length=120)
    device_uuid = models.UUIDField(unique=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="field_devices",
    )
    last_seen_at = models.DateTimeField(null=True, blank=True)
    is_trusted = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

