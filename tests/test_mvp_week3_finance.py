from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.test import Client as HttpClient
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.finance.services import (
    get_cost_breakdown,
    get_daily_pnl,
    get_event_trace,
    get_group_pnl,
    get_operating_pnl,
)
from apps.herd.models import Animal, HerdGroup
from apps.inventory.services import consume_input
from apps.milk.models import MilkingSession
from apps.milk.services import MilkRecord, register_milking
from apps.sync.services import ActionEventMessage, process_action_event
from tests.factories import create_tenant, seed_farm


def _action_message(*, farm, event_type: str, payload: dict, sequence: int = 1):
    data = {"farm_id": str(farm.id), **payload}
    return ActionEventMessage(
        event_id=uuid4(),
        tenant_id=None,
        device_id=uuid4(),
        actor_id=None,
        client_sequence=sequence,
        schema_version=1,
        event_type=event_type,
        occurred_at=timezone.now(),
        payload=data,
    )


@pytest.mark.django_db(transaction=True)
def test_finance_engine_segments_pnl_by_group_and_animal():
    tenant = create_tenant("finseg")

    with tenant_context(tenant):
        farm, group, animal, feed, _ = seed_farm()
        second_group = HerdGroup.objects.create(farm=farm, name="Secas")
        second_animal = Animal.objects.create(
            farm=farm,
            current_group=second_group,
            tag=f"B{uuid4().hex[:5]}",
            status=Animal.Status.LACTATING,
        )
        today = timezone.localdate()

        register_milking(
            farm=farm,
            milking_date=today,
            shift=MilkingSession.Shift.TOTAL_DAY,
            records=[
                MilkRecord(animal=animal, liters=Decimal("20")),
                MilkRecord(animal=second_animal, liters=Decimal("7")),
            ],
            unit_price=Decimal("0.50"),
            source_event_id=uuid4(),
        )
        consume_input(
            farm=farm,
            input_=feed,
            quantity=Decimal("2"),
            occurred_at=timezone.now(),
            animal=animal,
            group=group,
            source_event_id=uuid4(),
        )

        farm_pnl = get_operating_pnl(farm=farm, start_date=today, end_date=today)
        group_pnl = get_operating_pnl(
            farm=farm,
            group=group,
            start_date=today,
            end_date=today,
        )
        animal_pnl = get_operating_pnl(
            farm=farm,
            animal=animal,
            start_date=today,
            end_date=today,
        )
        second_group_pnl = get_operating_pnl(
            farm=farm,
            group=second_group,
            start_date=today,
            end_date=today,
        )

        assert farm_pnl.liters == Decimal("27")
        assert farm_pnl.revenue == Decimal("13.50")
        assert farm_pnl.costs == Decimal("37.0000")
        assert group_pnl.liters == Decimal("20")
        assert group_pnl.costs == Decimal("37.0000")
        assert group_pnl.cost_per_liter == Decimal("1.8500")
        assert animal_pnl.costs == Decimal("37.0000")
        assert second_group_pnl.liters == Decimal("7")
        assert second_group_pnl.costs == Decimal("0")


@pytest.mark.django_db(transaction=True)
def test_group_pnl_exposes_unassigned_costs_for_reconciliation():
    tenant = create_tenant("finunassigned")

    with tenant_context(tenant):
        farm, _, _, feed, _ = seed_farm()
        consume_input(
            farm=farm,
            input_=feed,
            quantity=Decimal("1"),
            occurred_at=timezone.now(),
            source_event_id=uuid4(),
        )

        group_rows = {row.label: row.pnl for row in get_group_pnl(farm=farm)}
        farm_pnl = get_operating_pnl(farm=farm)

        assert "Sin asignar" in group_rows
        assert group_rows["Sin asignar"].costs == Decimal("18.5000")
        assert farm_pnl.costs == group_rows["Sin asignar"].costs


@pytest.mark.django_db(transaction=True)
def test_finance_engine_returns_daily_pnl_and_cost_breakdown():
    tenant = create_tenant("findaily")

    with tenant_context(tenant):
        farm, _, animal, feed, medicine = seed_farm()
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)

        register_milking(
            farm=farm,
            milking_date=yesterday,
            shift=MilkingSession.Shift.TOTAL_DAY,
            records=[MilkRecord(animal=animal, liters=Decimal("6"))],
            unit_price=Decimal("0.45"),
            source_event_id=uuid4(),
        )
        register_milking(
            farm=farm,
            milking_date=today,
            shift=MilkingSession.Shift.TOTAL_DAY,
            records=[MilkRecord(animal=animal, liters=Decimal("10"))],
            unit_price=Decimal("0.45"),
            source_event_id=uuid4(),
        )
        consume_input(
            farm=farm,
            input_=feed,
            quantity=Decimal("1"),
            occurred_at=timezone.now(),
            animal=animal,
            group=animal.current_group,
            source_event_id=uuid4(),
        )
        consume_input(
            farm=farm,
            input_=medicine,
            quantity=Decimal("10"),
            occurred_at=timezone.now() - timedelta(days=1),
            animal=animal,
            group=animal.current_group,
            source_event_id=uuid4(),
        )

        daily_rows = get_daily_pnl(farm=farm, start_date=yesterday, end_date=today)
        costs = {row.cost_type: row for row in get_cost_breakdown(farm=farm)}

        assert [row.day for row in daily_rows] == [today, yesterday]
        assert daily_rows[0].pnl.liters == Decimal("10")
        assert daily_rows[0].pnl.costs == Decimal("18.5000")
        assert daily_rows[1].pnl.liters == Decimal("6")
        assert daily_rows[1].pnl.costs == Decimal("1.8000")
        assert costs["feed"].amount == Decimal("18.5000")
        assert costs["medicine"].amount == Decimal("1.8000")
        assert costs["feed"].percentage > costs["medicine"].percentage


@pytest.mark.django_db(transaction=True)
def test_event_trace_uses_action_queue_metadata():
    tenant = create_tenant("fintrace")

    with tenant_context(tenant):
        farm, group, animal, feed, _ = seed_farm()
        milk_event = _action_message(
            farm=farm,
            event_type="milk.milking_recorded",
            payload={
                "records": [{"animal_id": str(animal.id), "liters": "11"}],
                "shift": "total_day",
            },
            sequence=1,
        )
        feed_event = _action_message(
            farm=farm,
            event_type="inventory.input_consumed",
            payload={
                "group_id": str(group.id),
                "input_id": str(feed.id),
                "quantity": "1",
                "notes": "Balanceado sala",
            },
            sequence=2,
        )

        assert process_action_event(milk_event).status == "acked"
        assert process_action_event(feed_event).status == "acked"

        trace = {row.source_event_id: row for row in get_event_trace(farm=farm)}

        assert trace[milk_event.event_id].event_type == "milk.milking_recorded"
        assert trace[milk_event.event_id].status == "processed"
        assert trace[milk_event.event_id].liters == Decimal("11.000")
        assert trace[milk_event.event_id].revenue == Decimal("4.9500")
        assert trace[feed_event.event_id].event_type == "inventory.input_consumed"
        assert trace[feed_event.event_id].costs == Decimal("18.5000")


@pytest.mark.django_db(transaction=True)
def test_finance_dashboard_renders_for_tenant():
    tenant = create_tenant("finui")

    with tenant_context(tenant):
        farm, _, animal, _, _ = seed_farm()
        register_milking(
            farm=farm,
            milking_date=timezone.localdate(),
            shift=MilkingSession.Shift.TOTAL_DAY,
            records=[MilkRecord(animal=animal, liters=Decimal("9"))],
            source_event_id=uuid4(),
        )
        farm_id = farm.id

    client = HttpClient(HTTP_HOST=f"{tenant.schema_name}.localhost")

    response = client.get("/finanzas/")
    fragment = client.get(
        f"/finanzas/fragmento/?farm={farm_id}",
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert "Motor Financiero" in response.content.decode()
    assert fragment.status_code == 200
    assert "P&L diario" in fragment.content.decode()
