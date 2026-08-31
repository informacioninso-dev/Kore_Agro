from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel


class IncomingEvent(TimeStampedModel):
    class Status(models.TextChoices):
        RECEIVED = "received", "Recibido"
        PROCESSING = "processing", "Procesando"
        PROCESSED = "processed", "Procesado"
        FAILED = "failed", "Fallido"
        CONFLICT = "conflict", "Conflicto"

    event_id = models.UUIDField(primary_key=True, editable=False)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    device_id = models.UUIDField(db_index=True)
    actor_id = models.UUIDField(null=True, blank=True, db_index=True)
    client_sequence = models.PositiveBigIntegerField()
    schema_version = models.PositiveSmallIntegerField(default=1)
    event_type = models.CharField(max_length=100, db_index=True)
    occurred_at = models.DateTimeField()
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["client_sequence", "created_at"]
        indexes = [
            models.Index(fields=["device_id", "client_sequence"]),
            models.Index(fields=["event_type", "occurred_at"]),
            models.Index(fields=["status"]),
        ]

    def mark_processing(self) -> None:
        self.status = self.Status.PROCESSING
        self.error_code = ""
        self.error_message = ""
        self.save(update_fields=["status", "error_code", "error_message", "updated_at"])

    def mark_processed(self) -> None:
        self.status = self.Status.PROCESSED
        self.processed_at = timezone.now()
        self.save(update_fields=["status", "processed_at", "updated_at"])

    def mark_failed(self, *, code: str, message: str) -> None:
        self.status = self.Status.FAILED
        self.error_code = code[:80]
        self.error_message = message
        self.save(update_fields=["status", "error_code", "error_message", "updated_at"])

    def mark_conflict(self, *, code: str, message: str) -> None:
        self.status = self.Status.CONFLICT
        self.error_code = code[:80]
        self.error_message = message
        self.save(update_fields=["status", "error_code", "error_message", "updated_at"])

    def __str__(self) -> str:
        return f"{self.event_type} {self.event_id}"

