import uuid

from django.db import models
from django.utils import timezone


class UUIDPrimaryKeyModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ActorStampedModel(models.Model):
    created_by_id = models.UUIDField(null=True, blank=True)
    updated_by_id = models.UUIDField(null=True, blank=True)
    source_device_id = models.UUIDField(null=True, blank=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    is_active = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self) -> None:
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_active", "deleted_at", "updated_at"])


class TenantModel(UUIDPrimaryKeyModel, TimeStampedModel, ActorStampedModel):
    class Meta:
        abstract = True

