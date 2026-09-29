from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client as HttpClient
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context, tenant_context

from apps.configuration.models import (
    CapabilityDefinition,
    OrganizationCapability,
    OrganizationProfile,
    ProfileDefinition,
)
from apps.herd.models import Animal, Farm, HerdGroup
from apps.identity.access import ROLE_MANAGER, ensure_role_groups
from apps.inventory.models import Input, StockLot
from apps.tenants.models import Client, Domain

TEST_TENANT_CAPABILITIES = {
    "herd": ("Hato", CapabilityDefinition.Category.PRODUCTION),
    "milk": ("Produccion de leche", CapabilityDefinition.Category.PRODUCTION),
    "reproduction": ("Reproduccion", CapabilityDefinition.Category.PRODUCTION),
    "health": ("Sanidad", CapabilityDefinition.Category.PRODUCTION),
    "growth": ("Pesajes y crecimiento", CapabilityDefinition.Category.ANALYTICS),
    "grazing": ("Pastoreo y potreros", CapabilityDefinition.Category.PRODUCTION),
    "workforce": ("Personal y tareas", CapabilityDefinition.Category.OPERATIONS),
    "inventory": ("Inventario", CapabilityDefinition.Category.INVENTORY),
    "finance": ("Finanzas", CapabilityDefinition.Category.FINANCE),
    "documents": ("Documentos", CapabilityDefinition.Category.COMPLIANCE),
    "field_offline": ("Campo offline", CapabilityDefinition.Category.OPERATIONS),
}


def create_tenant(prefix: str = "tenant") -> Client:
    safe_prefix = "".join(char for char in prefix if char.isalnum())
    schema_name = f"{safe_prefix}{uuid4().hex[:10]}"
    with schema_context(get_public_schema_name()):
        tenant = Client.objects.create(schema_name=schema_name, name=f"Tenant {schema_name}")
        Domain.objects.create(domain=f"{schema_name}.localhost", tenant=tenant, is_primary=True)
        profile, _ = ProfileDefinition.objects.get_or_create(
            code="livestock",
            defaults={"name": "Ganaderia"},
        )
        OrganizationProfile.objects.update_or_create(
            organization=tenant,
            profile=profile,
            defaults={"is_active": True},
        )
        for index, (code, (name, category)) in enumerate(TEST_TENANT_CAPABILITIES.items()):
            capability, _ = CapabilityDefinition.objects.get_or_create(
                code=code,
                defaults={"name": name, "category": category, "sort_order": index * 10},
            )
            capability.compatible_profiles.add(profile)
            OrganizationCapability.objects.update_or_create(
                organization=tenant,
                capability=capability,
                defaults={
                    "status": OrganizationCapability.Status.ENABLED,
                    "expires_on": None,
                },
            )
    return tenant


def authenticated_client(tenant: Client, user) -> HttpClient:
    """Build a client session while the auth user is in its tenant schema."""
    client = HttpClient(HTTP_HOST=f"{tenant.schema_name}.localhost")
    with tenant_context(tenant):
        client.force_login(user)
    return client


def authenticated_manager_client(tenant: Client) -> HttpClient:
    """Build an HTTP client with a manager session in the tenant schema."""
    with tenant_context(tenant):
        ensure_role_groups()
        user = get_user_model().objects.create_user(
            username=f"manager-{uuid4().hex[:8]}",
            password="test-password",
        )
        user.groups.add(Group.objects.get(name=ROLE_MANAGER))

    return authenticated_client(tenant, user)


def seed_farm():
    farm = Farm.objects.create(
        name="Hacienda Test",
        code=f"HT{uuid4().hex[:4]}",
        default_milk_price=Decimal("0.45"),
    )
    group = HerdGroup.objects.create(farm=farm, name="Produccion")
    animal = Animal.objects.create(
        farm=farm,
        current_group=group,
        tag=f"A{uuid4().hex[:5]}",
        status=Animal.Status.LACTATING,
        last_calving_date=timezone.localdate() - timedelta(days=40),
    )
    feed = Input.objects.create(
        name="Balanceado test",
        sku=f"BAL-{uuid4().hex[:6]}",
        category=Input.Category.FEED,
        unit=Input.Unit.SACK,
        default_unit_cost=Decimal("18.50"),
    )
    medicine = Input.objects.create(
        name="Antibiotico test",
        sku=f"ATB-{uuid4().hex[:6]}",
        category=Input.Category.MEDICINE,
        unit=Input.Unit.ML,
        default_unit_cost=Decimal("0.18"),
        milk_withdrawal_hours=72,
    )
    StockLot.objects.create(
        farm=farm,
        input=feed,
        lot_code="T1",
        quantity_on_hand=Decimal("10"),
        unit_cost=Decimal("18.50"),
    )
    StockLot.objects.create(
        farm=farm,
        input=medicine,
        lot_code="M1",
        quantity_on_hand=Decimal("100"),
        unit_cost=Decimal("0.18"),
    )
    return farm, group, animal, feed, medicine
