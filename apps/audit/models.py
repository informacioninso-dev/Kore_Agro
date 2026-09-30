from django.conf import settings
from django.db import models

from apps.common.models import TenantModel


class AuditEvent(TenantModel):
    class Action(models.TextChoices):
        CREATE = "create", "Creacion"
        UPDATE = "update", "Actualizacion"
        DELETE = "delete", "Eliminacion"

    action = models.CharField(max_length=20, choices=Action.choices)
    model_label = models.CharField(max_length=120, db_index=True)
    object_id = models.CharField(max_length=80, db_index=True)
    object_repr = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    actor_username = models.CharField(max_length=150, blank=True)
    request_method = models.CharField(max_length=12, blank=True)
    request_path = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    source_event_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["model_label", "object_id", "created_at"]),
            models.Index(fields=["actor", "created_at"]),
        ]
        permissions = [("export_audit", "Puede exportar la auditoria")]

    def __str__(self) -> str:
        return f"{self.get_action_display()} {self.model_label} {self.object_id}"
