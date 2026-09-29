from uuid import UUID

from django.db.models import Q
from django.utils import timezone
from ninja import NinjaAPI
from ninja.errors import HttpError
from ninja.security import django_auth

from apps.configuration.access import request_capability_codes
from apps.grazing.models import GrazingPeriod, Paddock
from apps.health.services import active_milk_withdrawals, open_treatments
from apps.herd.models import Animal, HerdGroup
from apps.identity.access import (
    FIELD_ROLES,
    MANAGEMENT_ROLES,
    accessible_farms_for_user,
    require_api_role,
    user_has_any_role,
)
from apps.identity.models import FieldDevice
from apps.inventory.models import Input
from apps.reproduction.services import daily_reproduction_attention
from apps.workforce.models import Worker, WorkTask

from .schemas import ActionQueueResponseSchema, ActionQueueSchema
from .services import ActionEventMessage, process_action_queue

api = NinjaAPI(title="KORE AGRO Sync API", version="0.1.0", auth=django_auth)


def _validate_device(request) -> FieldDevice:
    require_api_role(request.auth, FIELD_ROLES)
    if "field_offline" not in request_capability_codes(request):
        raise HttpError(403, "El modulo de campo offline no esta habilitado.")
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
    capabilities = request_capability_codes(request)
    farm_queryset = accessible_farms_for_user(request.auth)
    farms = list(
        farm_queryset.values(
            "id",
            "name",
            "code",
            "default_milk_price",
        )
    )
    farm_ids = [farm["id"] for farm in farms]
    groups = list(
        HerdGroup.objects.filter(is_active=True, farm_id__in=farm_ids).values(
            "id",
            "farm_id",
            "name",
            "group_type",
        )
    )
    animals = list(
        Animal.objects.filter(is_active=True, farm_id__in=farm_ids).values(
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
    if not capabilities & {"health", "inventory"}:
        inputs = []
    paddocks = []
    active_grazing = []
    if "grazing" in capabilities:
        paddocks = list(
            Paddock.objects.filter(is_active=True, farm_id__in=farm_ids).values(
                "id",
                "farm_id",
                "name",
                "code",
                "area_hectares",
                "rest_target_days",
                "capacity_animals",
            )
        )
        active_grazing = list(
            GrazingPeriod.objects.filter(
                farm_id__in=farm_ids,
                ended_on__isnull=True,
            ).values(
                "id",
                "farm_id",
                "paddock_id",
                "paddock__name",
                "group_id",
                "group__name",
                "started_on",
            )
        )
    workers = []
    work_tasks = []
    if "workforce" in capabilities:
        worker_queryset = Worker.objects.filter(is_active=True, farm_id__in=farm_ids)
        is_manager = user_has_any_role(request.auth, MANAGEMENT_ROLES)
        if not is_manager:
            worker_queryset = worker_queryset.filter(user=request.auth)
        workers = list(
            worker_queryset.values(
                "id",
                "farm_id",
                "code",
                "full_name",
                "position",
            )
        )
        work_task_queryset = WorkTask.objects.filter(
            farm_id__in=farm_ids,
            status__in=(WorkTask.Status.PENDING, WorkTask.Status.IN_PROGRESS),
        )
        if not is_manager:
            work_task_queryset = work_task_queryset.filter(
                Q(assigned_to_id__in=[worker["id"] for worker in workers])
                | Q(assigned_to__isnull=True)
            )
        work_tasks = list(
            work_task_queryset.values(
                "id",
                "farm_id",
                "title",
                "category",
                "priority",
                "status",
                "assigned_to_id",
                "assigned_to__full_name",
                "scheduled_for",
            )
        )
    tenant = getattr(request, "tenant", None)
    attention = daily_reproduction_attention()
    today_actions = []
    for withdrawal in active_milk_withdrawals().filter(farm_id__in=farm_ids)[:6]:
        today_actions.append(
            {
                "kind": "withdrawal",
                "priority": "urgent",
                "farm_id": str(withdrawal.farm_id),
                "animal_id": str(withdrawal.animal_id),
                "title": f"Arete {withdrawal.animal.tag}: no entregar leche",
                "detail": (
                    f"Retiro activo por {withdrawal.reason} hasta {withdrawal.ends_at:%d/%m %H:%M}."
                ),
                "panel": "healthPanel",
            }
        )
    for animal in attention["dry_off"].filter(farm_id__in=farm_ids)[:6]:
        today_actions.append(
            {
                "kind": "dry_off",
                "priority": "important",
                "farm_id": str(animal.farm_id),
                "animal_id": str(animal.id),
                "title": f"Arete {animal.tag}: revisar secado",
                "detail": f"Parto esperado: {animal.expected_calving_date:%d/%m/%Y}.",
                "panel": "reproPanel",
            }
        )
    for animal in attention["pregnancy_checks"].filter(farm_id__in=farm_ids)[:6]:
        today_actions.append(
            {
                "kind": "pregnancy",
                "priority": "important",
                "farm_id": str(animal.farm_id),
                "animal_id": str(animal.id),
                "title": f"Arete {animal.tag}: revisar preñez",
                "detail": "Ya cumple el tiempo para diagnóstico de preñez.",
                "panel": "reproPanel",
            }
        )
    for treatment in open_treatments().filter(farm_id__in=farm_ids)[:6]:
        today_actions.append(
            {
                "kind": "treatment",
                "priority": "normal",
                "farm_id": str(treatment.farm_id),
                "animal_id": str(treatment.animal_id),
                "title": f"Arete {treatment.animal.tag}: tratamiento abierto",
                "detail": treatment.diagnosis,
                "panel": "healthPanel",
            }
        )
    panel_capabilities = {
        "healthPanel": "health",
        "reproPanel": "reproduction",
    }
    today_actions = [
        action
        for action in today_actions
        if panel_capabilities.get(action["panel"]) in capabilities
    ]
    return {
        "tenant": tenant.schema_name if tenant else None,
        "capabilities": sorted(capabilities),
        "farms": farms,
        "default_farm_id": str(farm_ids[0]) if farm_ids else None,
        "can_switch_farm": user_has_any_role(request.auth, MANAGEMENT_ROLES) and len(farms) > 1,
        "groups": groups,
        "animals": animals,
        "inputs": inputs,
        "paddocks": paddocks,
        "active_grazing": active_grazing,
        "workers": workers,
        "work_tasks": work_tasks,
        "today_actions": today_actions,
    }


@api.post("/sync/events", response=ActionQueueResponseSchema)
def sync_events(request, payload: ActionQueueSchema):
    device = _validate_device(request)
    capabilities = request_capability_codes(request)
    allowed_farm_ids = set(accessible_farms_for_user(request.auth).values_list("id", flat=True))
    allowed_worker_ids = None
    if not user_has_any_role(request.auth, MANAGEMENT_ROLES):
        allowed_worker_ids = set(
            Worker.objects.filter(
                user=request.auth,
                is_active=True,
                farm_id__in=allowed_farm_ids,
            ).values_list("id", flat=True)
        )
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
    results = process_action_queue(
        messages,
        allowed_farm_ids=allowed_farm_ids,
        allowed_capabilities=set(capabilities),
        allowed_worker_ids=allowed_worker_ids,
    )
    return {"results": [result.__dict__ for result in results]}
