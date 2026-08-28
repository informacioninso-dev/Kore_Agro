from ninja import NinjaAPI

from apps.herd.models import Animal, Farm, HerdGroup
from apps.inventory.models import Input

from .schemas import ActionQueueResponseSchema, ActionQueueSchema
from .services import ActionEventMessage, process_action_queue

api = NinjaAPI(title="KORE AGRO Sync API", version="0.1.0")


@api.get("/field/bootstrap")
def field_bootstrap(request):
    farms = list(
        Farm.objects.filter(is_active=True).values(
            "id",
            "name",
            "code",
            "default_milk_price",
        )
    )
    groups = list(
        HerdGroup.objects.filter(is_active=True).values(
            "id",
            "farm_id",
            "name",
            "group_type",
        )
    )
    animals = list(
        Animal.objects.filter(is_active=True).values(
            "id",
            "farm_id",
            "current_group_id",
            "tag",
            "name",
            "status",
            "last_calving_date",
            "expected_calving_date",
            "dry_off_date",
        )
    )
    inputs = list(
        Input.objects.filter(is_active=True).values(
            "id",
            "name",
            "sku",
            "category",
            "unit",
            "default_unit_cost",
            "milk_withdrawal_hours",
        )
    )
    tenant = getattr(request, "tenant", None)
    return {
        "tenant": tenant.schema_name if tenant else None,
        "farms": farms,
        "groups": groups,
        "animals": animals,
        "inputs": inputs,
    }


@api.post("/sync/events", response=ActionQueueResponseSchema)
def sync_events(request, payload: ActionQueueSchema):
    messages = [
        ActionEventMessage(
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
        for event in payload.events
    ]
    results = process_action_queue(messages)
    return {"results": [result.__dict__ for result in results]}
