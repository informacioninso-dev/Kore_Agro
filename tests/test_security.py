from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import Client as HttpClient
from django.test import override_settings
from django_tenants.utils import tenant_context
from pydantic import ValidationError as PydanticValidationError

from apps.dashboard.external_info import ExternalProviderError, _validate_external_url
from apps.herd.models import Farm
from apps.identity.access import ROLE_MANAGER, ensure_role_groups
from apps.identity.models import FieldDevice
from apps.sync.schemas import ActionQueueSchema
from tests.factories import create_tenant


def _manager(tenant, username="seguridad"):
    with tenant_context(tenant):
        ensure_role_groups()
        user = get_user_model().objects.create_user(
            username=username,
            password="Clave-Segura-2026!",
        )
        user.groups.add(Group.objects.get(name=ROLE_MANAGER))
        return user


@pytest.mark.django_db(transaction=True)
def test_tenant_login_rejects_external_redirects():
    cache.clear()
    tenant = create_tenant("securelogin")
    _manager(tenant)
    client = HttpClient(HTTP_HOST=f"{tenant.schema_name}.localhost")

    response = client.post(
        "/login/",
        {
            "username": "seguridad",
            "password": "Clave-Segura-2026!",
            "next": "https://evil.example/phishing",
        },
    )

    assert response.status_code == 302
    assert response.url == "/"


@pytest.mark.django_db(transaction=True)
@override_settings(LOGIN_FAILURE_LIMIT=3, LOGIN_IP_FAILURE_LIMIT=20)
def test_tenant_login_throttles_repeated_failures():
    cache.clear()
    tenant = create_tenant("throttlelogin")
    _manager(tenant)
    client = HttpClient(HTTP_HOST=f"{tenant.schema_name}.localhost")

    responses = [
        client.post("/login/", {"username": "seguridad", "password": "incorrecta"})
        for _ in range(3)
    ]

    assert [response.status_code for response in responses] == [200, 200, 429]
    assert "Demasiados intentos" in responses[-1].content.decode()


@pytest.mark.django_db(transaction=True)
def test_field_sync_enforces_csrf_with_session_authentication():
    tenant = create_tenant("fieldcsrf")
    user = _manager(tenant)
    client = HttpClient(
        HTTP_HOST=f"{tenant.schema_name}.localhost",
        enforce_csrf_checks=True,
    )
    with tenant_context(tenant):
        client.force_login(user)

    field_response = client.get("/field/")
    csrf_token = field_response.cookies["csrftoken"].value
    without_token = client.post(
        "/api/sync/events",
        data={"events": []},
        content_type="application/json",
        HTTP_X_KORE_DEVICE_ID=str(uuid4()),
    )
    with_token = client.post(
        "/api/sync/events",
        data={"events": []},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
        HTTP_X_KORE_DEVICE_ID=str(uuid4()),
    )

    assert without_token.status_code == 403
    assert with_token.status_code == 422
    assert "csrftoken" in field_response.cookies
    assert "data-csrf-token" not in field_response.content.decode()
    assert "data-storage-scope" in field_response.content.decode()


@pytest.mark.django_db(transaction=True)
@override_settings(KORE_MAX_FIELD_DEVICES_PER_USER=1)
def test_field_device_enrollment_is_bounded_per_user():
    tenant = create_tenant("devicelimit")
    user = _manager(tenant)
    with tenant_context(tenant):
        Farm.objects.create(name="Hacienda segura", code="SEGURA")
    client = HttpClient(HTTP_HOST=f"{tenant.schema_name}.localhost")
    with tenant_context(tenant):
        client.force_login(user)

    first = client.get("/api/field/bootstrap", HTTP_X_KORE_DEVICE_ID=str(uuid4()))
    second = client.get("/api/field/bootstrap", HTTP_X_KORE_DEVICE_ID=str(uuid4()))

    assert first.status_code == 200
    assert second.status_code == 429
    with tenant_context(tenant):
        assert FieldDevice.objects.filter(assigned_to=user).count() == 1


@override_settings(
    EXTERNAL_INFO_ALLOWED_HOSTS=["api.open-meteo.com", "datosabiertos.gob.ec"]
)
def test_external_information_blocks_ssrf_destinations():
    _validate_external_url("https://api.open-meteo.com/v1/forecast")
    _validate_external_url("https://www.datosabiertos.gob.ec/api/3/action/package_show")

    for url in (
        "http://api.open-meteo.com/v1/forecast",
        "https://127.0.0.1/internal",
        "https://datosabiertos.gob.ec.evil.example/file",
        "https://user:password@datosabiertos.gob.ec/file",
    ):
        with pytest.raises(ExternalProviderError):
            _validate_external_url(url)


def test_sync_batch_requires_between_one_and_one_hundred_events():
    with pytest.raises(PydanticValidationError):
        ActionQueueSchema(events=[])


@pytest.mark.django_db(transaction=True)
def test_security_headers_are_applied_to_responses():
    tenant = create_tenant("securityheaders")
    response = HttpClient(HTTP_HOST=f"{tenant.schema_name}.localhost").get("/health/")

    assert response.headers["Content-Security-Policy"].startswith("default-src 'self'")
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["Permissions-Policy"].startswith("camera=()")
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
