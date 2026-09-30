from celery import shared_task
from django_tenants.utils import get_public_schema_name, schema_context, tenant_context

from apps.tenants.models import Client

from .models import IncomingEvent
from .services import ActionEventMessage, process_action_event


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_incoming_event(self, schema_name: str, event_id: str):
    with schema_context(get_public_schema_name()):
        tenant = Client.objects.get(schema_name=schema_name)

    with tenant_context(tenant):
        event = IncomingEvent.objects.get(event_id=event_id)
        message = ActionEventMessage(
            event_id=event.event_id,
            tenant_id=event.tenant_id,
            device_id=event.device_id,
            actor_id=event.actor_id,
            occurred_at=event.occurred_at,
            event_type=event.event_type,
            payload=event.payload,
            client_sequence=event.client_sequence,
            schema_version=event.schema_version,
        )
        return process_action_event(message).__dict__
