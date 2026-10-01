from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django_tenants.utils import tenant_context

from apps.audit.models import AuditEvent
from apps.herd.models import Farm
from apps.identity.access import (
    ROLE_FIELD_WORKER,
    ROLE_MANAGER,
    ROLE_OWNER,
    ensure_role_groups,
)
from apps.identity.models import FieldAssignment
from tests.factories import authenticated_client, create_tenant


def _role_user(tenant, *, username: str, role: str):
    with tenant_context(tenant):
        ensure_role_groups()
        user = get_user_model().objects.create_user(
            username=username,
            password="Owner-Strong-2026!",
        )
        user.groups.add(Group.objects.get(name=role))
        return user


@pytest.mark.django_db(transaction=True)
def test_owner_uses_tenant_settings_instead_of_django_admin():
    tenant = create_tenant("settingsowner")
    owner = _role_user(tenant, username="propietario", role=ROLE_OWNER)
    with tenant_context(tenant):
        Farm.objects.create(name="Hacienda Principal", code="HP")
    client = authenticated_client(tenant, owner)

    response = client.get("/configuracion/")

    assert response.status_code == 200
    html = response.content.decode()
    assert "Configuracion" in html
    assert "Equipo y accesos" in html
    assert "Hacienda Principal" in html
    assert 'href="/admin/"' not in html


@pytest.mark.django_db(transaction=True)
def test_owner_updates_organization_details_with_audit():
    tenant = create_tenant("settingsorganization")
    owner = _role_user(tenant, username="owner-org", role=ROLE_OWNER)
    client = authenticated_client(tenant, owner)

    response = client.post(
        "/configuracion/organizacion/",
        {
            "organization-name": "Hacienda Los Andes",
            "organization-legal_name": "Agro Los Andes S.A.",
            "organization-ruc": "1799999999001",
            "organization-province": "Pichincha",
            "organization-city": "Quito",
        },
    )

    assert response.status_code == 302
    tenant.refresh_from_db()
    assert tenant.legal_name == "Agro Los Andes S.A."
    with tenant_context(tenant):
        event = AuditEvent.objects.get(model_label="tenants.client", object_id=str(tenant.id))
        assert event.actor_username == owner.username
        assert event.changes["legal_name"]["to"] == "Agro Los Andes S.A."


@pytest.mark.django_db(transaction=True)
def test_manager_can_update_farm_but_cannot_manage_organization_or_users():
    tenant = create_tenant("settingsmanager")
    manager = _role_user(tenant, username="administrador", role=ROLE_MANAGER)
    with tenant_context(tenant):
        farm = Farm.objects.create(name="Hacienda Inicial", code="HI")
    client = authenticated_client(tenant, manager)
    prefix = str(farm.id)

    response = client.post(
        f"/configuracion/haciendas/{farm.id}/",
        {
            f"{prefix}-name": "Hacienda Actualizada",
            f"{prefix}-code": "HA",
            f"{prefix}-province": "Cotopaxi",
            f"{prefix}-canton": "Latacunga",
            f"{prefix}-parish": "Mulalo",
            f"{prefix}-weather_location": "Mulalo",
            f"{prefix}-default_milk_price": "0.52",
        },
    )
    forbidden = client.post("/configuracion/organizacion/", {})

    assert response.status_code == 302
    assert response.url == "/configuracion/"
    assert forbidden.status_code == 302
    assert forbidden.url.startswith("/login/")
    with tenant_context(tenant):
        farm.refresh_from_db()
        assert farm.name == "Hacienda Actualizada"
        assert farm.weather_location == "Mulalo"
        assert farm.default_milk_price == Decimal("0.5200")


@pytest.mark.django_db(transaction=True)
def test_owner_creates_field_worker_with_farm_assignment_and_audit():
    tenant = create_tenant("settingsworker")
    owner = _role_user(tenant, username="dueno", role=ROLE_OWNER)
    with tenant_context(tenant):
        farm = Farm.objects.create(name="Hacienda Norte", code="NORTE")
    client = authenticated_client(tenant, owner)

    response = client.post(
        "/configuracion/usuarios/crear/",
        {
            "user-username": "mayordomo",
            "user-first_name": "Maria",
            "user-last_name": "Campo",
            "user-email": "maria@example.com",
            "user-role": ROLE_FIELD_WORKER,
            "user-farm": str(farm.id),
            "user-password": "Campo-Seguro-2026!",
            "user-is_active": "on",
        },
    )

    assert response.status_code == 302
    assert response.url == "/configuracion/"
    with tenant_context(tenant):
        worker = get_user_model().objects.get(username="mayordomo")
        assert worker.groups.filter(name=ROLE_FIELD_WORKER).exists()
        assert FieldAssignment.objects.get(user=worker).farm_id == farm.id
        event = AuditEvent.objects.get(model_label="auth.user", object_id=str(worker.id))
        assert event.actor_username == owner.username
        assert event.changes["snapshot"]["role"] == ROLE_FIELD_WORKER


@pytest.mark.django_db(transaction=True)
def test_owner_cannot_deactivate_or_remove_own_owner_role():
    tenant = create_tenant("settingsself")
    owner = _role_user(tenant, username="dueno-principal", role=ROLE_OWNER)
    client = authenticated_client(tenant, owner)

    response = client.post(
        f"/configuracion/usuarios/{owner.id}/",
        {
            "user-username": owner.username,
            "user-first_name": "",
            "user-last_name": "",
            "user-email": "",
            "user-role": ROLE_MANAGER,
            "user-farm": "",
            "user-password": "",
        },
    )

    assert response.status_code == 422
    with tenant_context(tenant):
        owner.refresh_from_db()
        assert owner.is_active is True
        assert owner.groups.filter(name=ROLE_OWNER).exists()
