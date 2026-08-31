from uuid import UUID

from django.utils import timezone
from ninja import NinjaAPI
from ninja.errors import HttpError
from ninja.security import django_auth

from apps.health.services import active_milk_withdrawals, open_treatments
from apps.herd.models import Animal, Farm, HerdGroup
from apps.identity.access import FIELD_ROLES, require_api_role
from apps.identity.models import FieldDevice
from apps.inventory.models import Input
from apps.reproduction.services import daily_reproduction_attention

from .schemas import ActionQueueResponseSchema, ActionQueueSchema
from .services import ActionEventMessage, process_action_queue

api = NinjaAPI(title="KORE AGRO Sync API", version="0.1.0", auth=django_auth)


def _validate_device(request) -> FieldDevice:
    require_api_role(request.auth, FIELD_ROLES)
    raw_device_id = request.headers.get("X-Kore-Device-ID")
    if not raw_device_id:
        raise HttpError(400, "X-Kore-Device-ID header is required.")
    try:
        device_id = UUID(raw_device_id)
    except ValueError as exc:
        raise HttpError(400, "X-Kore-Device-ID must be a UUID.") from exc

    device, created = FieldDevice.objects.get_or_create(
        device_uuid=device_id,
        defaults={"name": f"Dispositivo {str(device_id)[:8]}", "assigned_to": request.auth},
    )
    if not created and device.assigned_to_id not in (None, request.auth.id):
        raise HttpError(403, "Este dispositivo pertenece a otro usuario.")
    if not device.is_trusted:
        raise HttpError(403, "Este dispositivo no ha sido autorizado.")

    update_fields = ["last_seen_at", "updated_at"]
    if device.assigned_to_id is None:
        device.assigned_to = request.auth
        update_fields.append("assigned_to")
    device.last_seen_at = timezone.now()
    device.save(update_fields=update_fields)
    return device


@api.get("/field/bootstrap")
def field_bootstrap(request):
    _validate_device(request)
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
    attention = daily_reproduction_attention()
    today_actions = []
    for withdrawal in active_milk_withdrawals()[:6]:
        today_actions.append(
            {
                "kind": "withdrawal",
                "priority": "urgent",
                "animal_id": str(withdrawal.animal_id),
                "title": f"Arete {withdrawal.animal.tag}: no entregar leche",
                "detail": (
                    f"Retiro activo por {withdrawal.reason} "
                    f"hasta {withdrawal.ends_at:%d/%m %H:%M}."
                ),
                "panel": "healthPanel",
            }
        )
    for animal in attention["dry_off"][:6]:
        today_actions.append(
            {
                "kind": "dry_off",
                "priority": "important",
                "animal_id": str(animal.id),
                "title": f"Arete {animal.tag}: revisar secado",
                "detail": f"Parto esperado: {animal.expected_calving_date:%d/%m/%Y}.",
                "panel": "reproPanel",
            }
        )
    for animal in attention["pregnancy_checks"][:6]:
        today_actions.append(
            {
                "kind": "pregnancy",
                "priority": "important",
                "animal_id": str(animal.id),
                "title": f"Arete {animal.tag}: revisar preñez",
                "detail": "Ya cumple el tiempo para diagnóstico de preñez.",
                "panel": "reproPanel",
            }
        )
    for treatment in open_treatments()[:6]:
        today_actions.append(
            {
                "kind": "treatment",
                "priority": "normal",
                "animal_id": str(treatment.animal_id),
                "title": f"Arete {treatment.animal.tag}: tratamiento abierto",
                "detail": treatment.diagnosis,
                "panel": "healthPanel",
            }
        )
    return {
        "tenant": tenant.schema_name if tenant else None,
        "farms": farms,
        "groups": groups,
        "animals": animals,
        "inputs": inputs,
        "today_actions": today_actions,
    }


@api.post("/sync/events", response=ActionQueueResponseSchema)
def sync_events(request, payload: ActionQueueSchema):
    device = _validate_device(request)
    messages = [
        ActionEventMessage(
            event_id=event.event_id,
            tenant_id=event.tenant_id,
            device_id=device.device_uuid,
            actor_id=None,
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
