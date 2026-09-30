from .context import get_audit_context
from .models import AuditEvent


def record_audit_event(
    *,
    action: str,
    model_label: str,
    object_id: str,
    object_repr: str,
    changes: dict,
    source_event_id=None,
) -> AuditEvent:
    context = get_audit_context()
    return AuditEvent.objects.create(
        action=action,
        model_label=model_label,
        object_id=object_id,
        object_repr=object_repr[:255],
        changes=changes,
        actor_id=context.actor_id,
        actor_username=context.actor_username,
        request_method=context.request_method,
        request_path=context.request_path,
        ip_address=context.ip_address,
        source_event_id=source_event_id,
    )
