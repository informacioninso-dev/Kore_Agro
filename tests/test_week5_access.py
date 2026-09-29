from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client as HttpClient
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.herd.models import Animal, Farm, HerdGroup
from apps.identity.access import ROLE_FIELD_WORKER, ROLE_MANAGER, ensure_role_groups
from apps.identity.models import FieldAssignment, FieldDevice
from apps.sync.models import IncomingEvent
from tests.factories import authenticated_client, create_tenant, seed_farm


def _tenant_user(tenant, username: str, role: str):
    with tenant_context(tenant):
        ensure_role_groups()
        user = get_user_model().objects.create_user(username=username, password="safe-password")
        user.groups.add(Group.objects.get(name=role))
        return user


@pytest.mark.django_db(transaction=True)
def test_dashboard_requires_an_authenticated_manager():
    tenant = create_tenant("accessmgr")
    client = HttpClient(HTTP_HOST=f"{tenant.schema_name}.localhost")

    response = client.get("/")

    assert response.status_code == 302
    assert response.url.startswith("/login/")


@pytest.mark.django_db(transaction=True)
def test_field_worker_can_use_field_app_but_not_management_dashboard():
    tenant = create_tenant("accessfield")
    user = _tenant_user(tenant, "mayordomo", ROLE_FIELD_WORKER)
    client = authenticated_client(tenant, user)

    field_response = client.get("/field/")
    dashboard_response = client.get("/")

    assert field_response.status_code == 200
    assert dashboard_response.status_code == 302
    assert dashboard_response.url.startswith("/login/")

    field_html = field_response.content.decode()
    for form_id in (
        "milkForm",
        "reproForm",
        "healthForm",
        "weightForm",
        "grazingForm",
        "taskForm",
        "inventoryForm",
        "receiptForm",
        "adjustmentForm",
        "expenseForm",
        "saleForm",
    ):
        assert f'id="{form_id}"' in field_html
    assert field_html.count('class="actionIcon"') == 11
    assert 'id="farmSelect"' in field_html
    assert 'name="farm_id"' not in field_html


@pytest.mark.django_db(transaction=True)
def test_field_bootstrap_requires_role_and_registers_its_device():
    tenant = create_tenant("accessapi")
    user = _tenant_user(tenant, "administrador", ROLE_MANAGER)
    device_id = uuid4()
    with tenant_context(tenant):
        Farm.objects.create(name="Hacienda norte", code="NORTE")
        Farm.objects.create(name="Hacienda sur", code="SUR")
    client = authenticated_client(tenant, user)

    response = client.get("/api/field/bootstrap", HTTP_X_KORE_DEVICE_ID=str(device_id))

    assert response.status_code == 200
    assert len(response.json()["farms"]) == 2
    assert response.json()["can_switch_farm"] is True
    assert "today_actions" in response.json()
    with tenant_context(tenant):
        device = FieldDevice.objects.get(device_uuid=device_id)
        assert device.assigned_to_id == user.id
        assert device.is_trusted is True


@pytest.mark.django_db(transaction=True)
def test_field_worker_bootstrap_only_contains_the_assigned_farm():
    tenant = create_tenant("fieldassignment")
    user = _tenant_user(tenant, "trabajador", ROLE_FIELD_WORKER)
    device_id = uuid4()
    with tenant_context(tenant):
        assigned_farm, assigned_group, assigned_animal, _, _ = seed_farm()
        other_farm = Farm.objects.create(name="Hacienda vecina", code="VECINA")
        other_group = HerdGroup.objects.create(farm=other_farm, name="Lote vecino")
        Animal.objects.create(farm=other_farm, current_group=other_group, tag="V-001")
        FieldAssignment.objects.create(user=user, farm=assigned_farm)
    client = authenticated_client(tenant, user)

    response = client.get("/api/field/bootstrap", HTTP_X_KORE_DEVICE_ID=str(device_id))

    assert response.status_code == 200
    payload = response.json()
    assert [farm["id"] for farm in payload["farms"]] == [str(assigned_farm.id)]
    assert {group["id"] for group in payload["groups"]} == {str(assigned_group.id)}
    assert {animal["id"] for animal in payload["animals"]} == {str(assigned_animal.id)}
    assert payload["default_farm_id"] == str(assigned_farm.id)
    assert payload["can_switch_farm"] is False


@pytest.mark.django_db(transaction=True)
def test_field_worker_cannot_sync_an_event_for_another_farm():
    tenant = create_tenant("fieldsyncaccess")
    user = _tenant_user(tenant, "trabajador-sync", ROLE_FIELD_WORKER)
    device_id = uuid4()
    with tenant_context(tenant):
        assigned_farm, _, _, feed, _ = seed_farm()
        other_farm = Farm.objects.create(name="Hacienda sin acceso", code="NOACCESS")
        FieldAssignment.objects.create(user=user, farm=assigned_farm)
    client = authenticated_client(tenant, user)

    response = client.post(
        "/api/sync/events",
        data={
            "events": [
                {
                    "event_id": str(uuid4()),
                    "device_id": str(device_id),
                    "actor_id": None,
                    "tenant_id": None,
                    "occurred_at": timezone.now().isoformat(),
                    "event_type": "inventory.input_consumed",
                    "payload": {
                        "farm_id": str(other_farm.id),
                        "input_id": str(feed.id),
                        "quantity": "1",
                    },
                    "client_sequence": 1,
                    "schema_version": 1,
                }
            ]
        },
        content_type="application/json",
        HTTP_X_KORE_DEVICE_ID=str(device_id),
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "failed"
    assert "No tienes acceso" in response.json()["results"][0]["detail"]
    with tenant_context(tenant):
        assert IncomingEvent.objects.count() == 0
