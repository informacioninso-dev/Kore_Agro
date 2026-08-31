from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.finance.models import CostAllocation, RevenueEntry
from apps.finance.services import get_operating_pnl
from apps.health.models import MilkWithdrawal, Treatment
from apps.herd.models import Animal, Farm
from apps.inventory.models import InventoryMovement, StockLot
from apps.milk.models import MilkYield
from apps.sync.models import IncomingEvent
from apps.sync.services import ActionEventMessage, process_action_event
from tests.factories import authenticated_manager_client, create_tenant, seed_farm


@pytest.mark.django_db(transaction=True)
def test_tenant_schema_isolation():
    tenant_a = create_tenant("isol_a")
    tenant_b = create_tenant("isol_b")

    with tenant_context(tenant_a):
        Farm.objects.create(name="Hacienda A", code="A001")
        assert Farm.objects.count() == 1

    with tenant_context(tenant_b):
        assert Farm.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_milking_event_is_idempotent_and_generates_revenue():
    tenant = create_tenant("milk")

    with tenant_context(tenant):
        farm, _, animal, _, _ = seed_farm()
        message = ActionEventMessage(
            event_id=uuid4(),
            tenant_id=None,
            device_id=uuid4(),
            actor_id=None,
            client_sequence=1,
            schema_version=1,
            event_type="milk.milking_recorded",
            occurred_at=timezone.now(),
            payload={
                "farm_id": str(farm.id),
                "records": [{"animal_id": str(animal.id), "liters": "12.5"}],
                "shift": "total_day",
            },
        )

        first = process_action_event(message)
        second = process_action_event(message)
        pnl = get_operating_pnl(farm=farm)

        assert first.status == "acked"
        assert second.detail == "already_processed"
        assert IncomingEvent.objects.count() == 1
        assert MilkYield.objects.count() == 1
        assert RevenueEntry.objects.count() == 1
        assert pnl.liters == Decimal("12.500")
        assert pnl.revenue == Decimal("5.6250")


@pytest.mark.django_db(transaction=True)
def test_inventory_consumption_decrements_stock_and_updates_pnl():
    tenant = create_tenant("stock")

    with tenant_context(tenant):
        farm, _, _, feed, _ = seed_farm()
        message = ActionEventMessage(
            event_id=uuid4(),
            tenant_id=None,
            device_id=uuid4(),
            actor_id=None,
            client_sequence=1,
            schema_version=1,
            event_type="inventory.input_consumed",
            occurred_at=timezone.now(),
            payload={
                "farm_id": str(farm.id),
                "input_id": str(feed.id),
                "quantity": "2",
                "notes": "Consumo prueba",
            },
        )

        result = process_action_event(message)
        stock = StockLot.objects.get(farm=farm, input=feed)
        pnl = get_operating_pnl(farm=farm)

        assert result.status == "acked"
        assert stock.quantity_on_hand == Decimal("8.000")
        assert InventoryMovement.objects.count() == 1
        assert CostAllocation.objects.count() == 1
        assert pnl.costs == Decimal("37.0000")
        assert pnl.net_profit == Decimal("-37.0000")


@pytest.mark.django_db(transaction=True)
def test_treatment_event_creates_milk_withdrawal_and_cost():
    tenant = create_tenant("health")

    with tenant_context(tenant):
        farm, _, animal, _, medicine = seed_farm()
        occurred_at = timezone.now()
        message = ActionEventMessage(
            event_id=uuid4(),
            tenant_id=None,
            device_id=uuid4(),
            actor_id=None,
            client_sequence=1,
            schema_version=1,
            event_type="health.treatment_recorded",
            occurred_at=occurred_at,
            payload={
                "farm_id": str(farm.id),
                "animal_id": str(animal.id),
                "input_id": str(medicine.id),
                "quantity": "10",
                "diagnosis": "Mastitis",
                "dosage": "10 ml",
            },
        )

        result = process_action_event(message)
        withdrawal = MilkWithdrawal.objects.get(animal=animal)
        pnl = get_operating_pnl(farm=farm)

        assert result.status == "acked"
        assert Treatment.objects.count() == 1
        assert withdrawal.ends_at == occurred_at + timedelta(hours=72)
        assert pnl.costs == Decimal("1.8000")


@pytest.mark.django_db(transaction=True)
def test_htmx_master_data_can_create_animal():
    tenant = create_tenant("crud")

    with tenant_context(tenant):
        farm, group, _, _, _ = seed_farm()

    client = authenticated_manager_client(tenant)
    response = client.post(
        "/datos/animales/crear/",
        data={
            "farm": str(farm.id),
            "current_group": str(group.id),
            "tag": "CRUD-001",
            "name": "Vaca CRUD",
            "sex": Animal.Sex.FEMALE,
            "status": Animal.Status.LACTATING,
            "is_active": "on",
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    with tenant_context(tenant):
        assert Animal.objects.filter(tag="CRUD-001").exists()
