from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.common.models import TenantModel

from .context import get_audit_context
from .models import AuditEvent

IGNORED_FIELDS = {
    "created_at",
    "updated_at",
    "created_by_id",
    "updated_by_id",
    "source_device_id",
}


def _is_auditable(sender) -> bool:
    return (
        isinstance(sender, type)
        and issubclass(sender, TenantModel)
        and sender is not AuditEvent
        and not sender._meta.abstract
    )


def _json_value(value):
    if isinstance(value, (date, datetime, time, Decimal, UUID)):
        return str(value)
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def _snapshot(instance) -> dict:
    values = {}
    for field in instance._meta.concrete_fields:
        if field.name in IGNORED_FIELDS:
            continue
        values[field.name] = _json_value(getattr(instance, field.attname, None))
    return values


def _safe_repr(instance) -> str:
    try:
        return str(instance)[:255]
    except Exception:  # pragma: no cover - defensive around third-party models
        return f"{instance._meta.label} {instance.pk}"[:255]


def _record(instance, action: str, changes: dict) -> None:
    context = get_audit_context()
    source_event_id = getattr(instance, "source_event_id", None)
    AuditEvent.objects.create(
        action=action,
        model_label=instance._meta.label_lower,
        object_id=str(instance.pk),
        object_repr=_safe_repr(instance),
        changes=changes,
        actor_id=context.actor_id,
        actor_username=context.actor_username,
        request_method=context.request_method,
        request_path=context.request_path,
        ip_address=context.ip_address,
        source_event_id=source_event_id,
    )


@receiver(pre_save)
def capture_previous_values(sender, instance, raw=False, **kwargs):
    if raw or not _is_auditable(sender) or not instance.pk:
        return
    previous = sender.objects.filter(pk=instance.pk).first()
    instance._audit_previous_values = _snapshot(previous) if previous else None


@receiver(post_save)
def record_saved_model(sender, instance, created=False, raw=False, **kwargs):
    if raw or not _is_auditable(sender):
        return
    after = _snapshot(instance)
    if created:
        _record(instance, AuditEvent.Action.CREATE, {"snapshot": after})
        return

    before = getattr(instance, "_audit_previous_values", None)
    if before is None:
        return
    changes = {
        field: {"from": before.get(field), "to": value}
        for field, value in after.items()
        if before.get(field) != value
    }
    if changes:
        _record(instance, AuditEvent.Action.UPDATE, changes)


@receiver(post_delete)
def record_deleted_model(sender, instance, **kwargs):
    if not _is_auditable(sender):
        return
    _record(instance, AuditEvent.Action.DELETE, {"snapshot": _snapshot(instance)})
