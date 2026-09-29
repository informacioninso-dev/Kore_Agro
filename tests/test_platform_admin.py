from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client as HttpClient
from django_tenants.utils import get_public_schema_name, schema_context, tenant_context

from apps.configuration.models import (
    CapabilityDefinition,
    OrganizationCapability,
    OrganizationProfile,
    ProfileDefinition,
)
from apps.identity.access import ROLE_OWNER
from apps.tenants.models import Client, Domain


def _platform_client(*, superuser: bool = True):
    with schema_context(get_public_schema_name()):
        platform, _ = Client.objects.get_or_create(
            schema_name=get_public_schema_name(),
            defaults={"name": "KORE Agro Plataforma", "on_trial": False},
        )
        Domain.objects.update_or_create(
            domain="platform.localhost",
            defaults={"tenant": platform, "is_primary": True},
        )
        username = f"platform-{uuid4().hex[:8]}"
        if superuser:
            user = get_user_model().objects.create_superuser(
                username=username,
                password="platform-test-password",
            )
        else:
            user = get_user_model().objects.create_user(
                username=username,
                password="platform-test-password",
            )
    client = HttpClient(HTTP_HOST="platform.localhost")
    with schema_context(get_public_schema_name()):
        client.force_login(user)
    return client


def _collection_center_catalog():
    profile, _ = ProfileDefinition.objects.get_or_create(
        code="collection_center",
        defaults={"name": "Centro de Acopio", "sort_order": 40},
    )
    capabilities = {}
    for index, (code, name, category) in enumerate(
        [
            ("counterparties", "Productores y contrapartes", "foundation"),
            ("weighing", "Pesaje operativo", "operations"),
            ("reception", "Recepcion de producto", "operations"),
            ("quality", "Control de calidad", "operations"),
            ("settlements", "Liquidaciones", "finance"),
        ]
    ):
        capability, _ = CapabilityDefinition.objects.get_or_create(
            code=code,
            defaults={"name": name, "category": category, "sort_order": index * 10},
        )
        capability.compatible_profiles.add(profile)
        capabilities[code] = capability
    capabilities["reception"].dependencies.set(
        [capabilities["counterparties"], capabilities["weighing"]]
    )
    capabilities["quality"].dependencies.set([capabilities["reception"]])
    capabilities["settlements"].dependencies.set(
        [capabilities["reception"], capabilities["quality"]]
    )
    return profile, capabilities["settlements"]


@pytest.mark.django_db(transaction=True)
def test_platform_dashboard_requires_public_superuser():
    anonymous = HttpClient(HTTP_HOST="platform.localhost")
    with schema_context(get_public_schema_name()):
        platform, _ = Client.objects.get_or_create(
            schema_name=get_public_schema_name(),
            defaults={"name": "KORE Agro Plataforma", "on_trial": False},
        )
        Domain.objects.update_or_create(
            domain="platform.localhost",
            defaults={"tenant": platform, "is_primary": True},
        )

    anonymous_response = anonymous.get("/")
    regular_response = _platform_client(superuser=False).get("/")
    superuser_response = _platform_client().get("/")

    assert anonymous_response.status_code == 302
    assert anonymous_response.url.startswith("/login/")
    assert regular_response.status_code == 403
    assert superuser_response.status_code == 200
    assert "Control de plataforma" in superuser_response.content.decode()


@pytest.mark.django_db(transaction=True)
def test_superuser_provisions_organization_profiles_capabilities_and_owner():
    client = _platform_client()
    with schema_context(get_public_schema_name()):
        profile, settlement = _collection_center_catalog()
        schema_name = f"acopio{uuid4().hex[:8]}"

    response = client.post(
        "/organizaciones/nueva/",
        {
            "name": "Acopio Sierra",
            "legal_name": "Acopio Sierra S.A.",
            "ruc": "1799999999002",
            "province": "Pichincha",
            "city": "Cayambe",
            "schema_name": schema_name,
            "domain": f"{schema_name}.localhost",
            "on_trial": "on",
            "profiles": [str(profile.id)],
            "capabilities": [str(settlement.id)],
            "owner_username": "propietario",
            "owner_email": "owner@example.com",
            "owner_password": "owner-test-password",
        },
    )

    assert response.status_code == 302
    with schema_context(get_public_schema_name()):
        organization = Client.objects.get(schema_name=schema_name)
        assert Domain.objects.get(tenant=organization, is_primary=True).domain == (
            f"{schema_name}.localhost"
        )
        assert OrganizationProfile.objects.get(
            organization=organization,
            profile=profile,
        ).is_active
        capability_codes = set(
            OrganizationCapability.objects.filter(organization=organization).values_list(
                "capability__code",
                flat=True,
            )
        )
        assert {
            "counterparties",
            "weighing",
            "reception",
            "quality",
            "settlements",
        }.issubset(capability_codes)
        assert not OrganizationCapability.objects.filter(
            organization=organization,
        ).exclude(status=OrganizationCapability.Status.TRIAL)

    with tenant_context(organization):
        owner = get_user_model().objects.get(username="propietario")
        assert owner.groups.filter(name=ROLE_OWNER).exists()
        assert Group.objects.filter(name=ROLE_OWNER).exists()


@pytest.mark.django_db(transaction=True)
def test_platform_catalog_exposes_seeded_profiles_and_capabilities():
    with schema_context(get_public_schema_name()):
        _collection_center_catalog()
        profile, _ = ProfileDefinition.objects.get_or_create(
            code="livestock",
            defaults={"name": "Ganaderia"},
        )
        capability, _ = CapabilityDefinition.objects.get_or_create(
            code="growth",
            defaults={
                "name": "Pesajes y crecimiento",
                "category": CapabilityDefinition.Category.PRODUCTION,
            },
        )
        capability.compatible_profiles.add(profile)
    response = _platform_client().get("/catalogo/")

    assert response.status_code == 200
    html = response.content.decode()
    assert "Ganaderia" in html
    assert "Centro de Acopio" in html
    assert "Pesajes y crecimiento" in html
