from datetime import datetime
from typing import Any
from uuid import UUID

from ninja import Schema
from pydantic import Field


class ActionEventSchema(Schema):
    event_id: UUID
    tenant_id: UUID | None = None
    device_id: UUID
    actor_id: UUID | None = None
    occurred_at: datetime
    event_type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any]
    client_sequence: int = Field(gt=0)
    schema_version: int = Field(default=1, gt=0)


class ActionQueueSchema(Schema):
    events: list[ActionEventSchema]


class EventAckSchema(Schema):
    event_id: UUID
    status: str
    detail: str = ""
    retryable: bool = False
    resolution: str = ""


class ActionQueueResponseSchema(Schema):
    results: list[EventAckSchema]
