from datetime import datetime
from typing import Any
from uuid import UUID

from ninja import Schema


class ActionEventSchema(Schema):
    event_id: UUID
    tenant_id: UUID | None = None
    device_id: UUID
    actor_id: UUID | None = None
    occurred_at: datetime
    event_type: str
    payload: dict[str, Any]
    client_sequence: int
    schema_version: int = 1


class ActionQueueSchema(Schema):
    events: list[ActionEventSchema]


class EventAckSchema(Schema):
    event_id: UUID
    status: str
    detail: str = ""


class ActionQueueResponseSchema(Schema):
    results: list[EventAckSchema]

