from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context

from apps.herd.models import Animal, Farm, HerdGroup
from apps.inventory.models import Input, StockLot
from apps.tenants.models import Client, Domain


def create_tenant(prefix: str = "tenant") -> Client:
    safe_prefix = "".join(char for char in prefix if char.isalnum())
    schema_name = f"{safe_prefix}{uuid4().hex[:10]}"
    with schema_context(get_public_schema_name()):
        tenant = Client.objects.create(schema_name=schema_name, name=f"Tenant {schema_name}")
        Domain.objects.create(domain=f"{schema_name}.localhost", tenant=tenant, is_primary=True)
    return tenant


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
