from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client as HttpClient
from django_tenants.utils import tenant_context

from apps.identity.access import ROLE_FIELD_WORKER, ROLE_MANAGER, ensure_role_groups
from apps.identity.models import FieldDevice
from tests.factories import authenticated_client, create_tenant


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


@pytest.mark.django_db(transaction=True)
def test_field_bootstrap_requires_role_and_registers_its_device():
    tenant = create_tenant("accessapi")
    user = _tenant_user(tenant, "administrador", ROLE_MANAGER)
    device_id = uuid4()
    client = authenticated_client(tenant, user)

    response = client.get("/api/field/bootstrap", HTTP_X_KORE_DEVICE_ID=str(device_id))

    assert response.status_code == 200
    assert "today_actions" in response.json()
    with tenant_context(tenant):
        device = FieldDevice.objects.get(device_uuid=device_id)
        assert device.assigned_to_id == user.id
        assert device.is_trusted is True
