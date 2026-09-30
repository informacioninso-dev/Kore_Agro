from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditContext:
    actor_id: int | None = None
    actor_username: str = ""
    request_method: str = ""
    request_path: str = ""
    ip_address: str | None = None


_current_audit_context = ContextVar("kore_audit_context", default=None)


def get_audit_context() -> AuditContext:
    return _current_audit_context.get() or AuditContext()


def set_audit_context(context: AuditContext):
    return _current_audit_context.set(context)


def reset_audit_context(token) -> None:
    _current_audit_context.reset(token)
