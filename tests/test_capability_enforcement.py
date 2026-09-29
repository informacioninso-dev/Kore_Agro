from uuid import uuid4

import pytest
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context, tenant_context

from apps.configuration.models import OrganizationCapability
from apps.growth.models import WeightRecord
from apps.identity.models import FieldDevice
from apps.sync.models import IncomingEvent
from tests.factories import authenticated_manager_client, create_tenant, seed_farm


def _suspend_capability(tenant, code: str) -> None:
    with schema_context(get_public_schema_name()):
        assignment = OrganizationCapability.objects.get(
            organization=tenant,
            capability__code=code,
        )
        assignment.status = OrganizationCapability.Status.SUSPENDED
        assignment.save(update_fields=["status"])


@pytest.mark.django_db(transaction=True)
def test_tenant_menu_and_route_follow_enabled_capabilities():
    tenant = create_tenant("contextmenu")
    client = authenticated_manager_client(tenant)
    _suspend_capability(tenant, "growth")

    home_response = client.get("/")
    growth_response = client.get("/crecimiento/")
    finance_response = client.get("/finanzas/")

    assert home_response.status_code == 200
    assert "Pesos y crecimiento" not in home_response.content.decode()
    assert "Produccion y cuentas" in home_response.content.decode()
    assert growth_response.status_code == 403
    assert "no esta habilitado" in growth_response.content.decode()
    assert finance_response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_inventory_only_tenant_keeps_farms_and_hides_herd_tools():
    tenant = create_tenant("inventoryonly")
    client = authenticated_manager_client(tenant)
    _suspend_capability(tenant, "herd")

    response = client.get("/datos/")
    group_create_response = client.post("/datos/lotes/crear/", data={})

    assert response.status_code == 200
    html = response.content.decode()
    assert "Haciendas" in html
    assert "Insumos" in html
    assert ">Hato<" not in html
    assert ">Lotes<" not in html
    assert group_create_response.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_field_app_and_api_require_offline_capability():
    tenant = create_tenant("fielddisabled")
    client = authenticated_manager_client(tenant)
    _suspend_capability(tenant, "field_offline")

    page_response = client.get("/field/")
    api_response = client.get(
        "/api/field/bootstrap",
        HTTP_X_KORE_DEVICE_ID=str(uuid4()),
    )

    assert page_response.status_code == 403
    assert api_response.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_field_bootstrap_only_advertises_enabled_modules():
    tenant = create_tenant("fieldmodules")
    client = authenticated_manager_client(tenant)
    _suspend_capability(tenant, "milk")

    response = client.get(
        "/api/field/bootstrap",
        HTTP_X_KORE_DEVICE_ID=str(uuid4()),
    )

    assert response.status_code == 200
    assert "field_offline" in response.json()["capabilities"]
    assert "milk" not in response.json()["capabilities"]


@pytest.mark.django_db(transaction=True)
def test_sync_rejects_event_for_suspended_capability_before_registration():
    tenant = create_tenant("eventsdisabled")
    client = authenticated_manager_client(tenant)
    with tenant_context(tenant):
        farm, _, animal, _, _ = seed_farm()
    _suspend_capability(tenant, "growth")
    device_id = uuid4()

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
                    "event_type": "growth.weight_recorded",
                    "payload": {
                        "farm_id": str(farm.id),
                        "animal_id": str(animal.id),
                        "weight_kg": "350.50",
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
    result = response.json()["results"][0]
    assert result["status"] == "failed"
    assert "growth" in result["detail"]
    with tenant_context(tenant):
        assert FieldDevice.objects.filter(device_uuid=device_id).exists()
        assert IncomingEvent.objects.count() == 0
        assert WeightRecord.objects.count() == 0
