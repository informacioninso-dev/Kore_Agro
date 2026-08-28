from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.test import Client as HttpClient
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.finance.models import CostAllocation, OperatingPeriodSnapshot, RevenueEntry
from apps.finance.services import get_event_trace, get_operating_pnl
from apps.finance.tasks import close_operating_periods
from apps.health.services import record_treatment
from apps.herd.models import Animal
from apps.inventory.models import InventoryMovement, StockLot
from apps.inventory.services import adjust_stock, receive_input
from apps.milk.models import MilkingSession, MilkYield
from apps.milk.services import MilkRecord, register_milking_detailed
from apps.sync.services import ActionEventMessage, process_action_event
from tests.factories import create_tenant, seed_farm


def _action_message(*, farm, event_type: str, payload: dict, sequence: int = 1):
    return ActionEventMessage(
        event_id=uuid4(),
        tenant_id=None,
        device_id=uuid4(),
        actor_id=None,
        client_sequence=sequence,
        schema_version=1,
        event_type=event_type,
        occurred_at=timezone.now(),
        payload={"farm_id": str(farm.id), **payload},
    )


@pytest.mark.django_db(transaction=True)
def test_input_receipt_feeds_stock_without_touching_the_pnl():
    tenant = create_tenant("receipt")

    with tenant_context(tenant):
        farm, _, _, feed, _ = seed_farm()

        receipt = receive_input(
            farm=farm,
            input_=feed,
            quantity=Decimal("10"),
            unit_cost=Decimal("20.50"),
            lot_code="T1",
        )
        stock = StockLot.objects.get(id=receipt.stock_lot_id)
        pnl = get_operating_pnl(farm=farm)

        assert stock.quantity_on_hand == Decimal("20.000")
        # 10 @ 18.50 already on hand + 10 @ 20.50 received -> weighted 19.50
        assert stock.unit_cost == Decimal("19.5000")
        assert InventoryMovement.objects.filter(
            movement_type=InventoryMovement.MovementType.IN
        ).count() == 1
        assert CostAllocation.objects.count() == 0
        assert pnl.costs == Decimal("0")


@pytest.mark.django_db(transaction=True)
def test_negative_stock_adjustment_books_shrinkage_cost():
    tenant = create_tenant("shrink")

    with tenant_context(tenant):
        farm, group, _, feed, _ = seed_farm()

        adjustment = adjust_stock(
            farm=farm,
            input_=feed,
            quantity_delta=Decimal("-2"),
            reason="Conteo fisico bodega",
        )
        stock = StockLot.objects.get(farm=farm, input=feed)
        allocation = CostAllocation.objects.get()
        movement = InventoryMovement.objects.get()
        pnl = get_operating_pnl(farm=farm)

        assert adjustment.recognized_cost == Decimal("37.0000")
        assert stock.quantity_on_hand == Decimal("8.000")
        assert allocation.cost_type == CostAllocation.CostType.SHRINKAGE
        assert allocation.amount == Decimal("37.0000")
        assert movement.movement_type == InventoryMovement.MovementType.ADJUSTMENT
        assert movement.quantity == Decimal("-2.000")
        assert pnl.costs == Decimal("37.0000")

        surplus = adjust_stock(
            farm=farm,
            input_=feed,
            quantity_delta=Decimal("1"),
            reason="Sobrante encontrado",
            group=group,
        )
        stock.refresh_from_db()

        assert surplus.recognized_cost == Decimal("0")
        assert stock.quantity_on_hand == Decimal("9.000")
        assert CostAllocation.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_milk_under_withdrawal_is_discarded_and_never_becomes_revenue():
    tenant = create_tenant("withdraw")

    with tenant_context(tenant):
        farm, _, animal, _, medicine = seed_farm()
        today = timezone.localdate()

        record_treatment(
            farm=farm,
            animal=animal,
            diagnosis="Mastitis",
            started_at=timezone.now(),
            input_=medicine,
            quantity=Decimal("10"),
        )
        result = register_milking_detailed(
            farm=farm,
            milking_date=today,
            shift=MilkingSession.Shift.TOTAL_DAY,
            records=[MilkRecord(animal=animal, liters=Decimal("12"))],
            unit_price=Decimal("0.50"),
            source_event_id=uuid4(),
        )
        yield_row = MilkYield.objects.get()
        pnl = get_operating_pnl(farm=farm, start_date=today, end_date=today)

        assert yield_row.is_discarded is True
        assert yield_row.discard_reason.startswith("Retiro de leche")
        assert result.discarded_liters == Decimal("12")
        assert result.saleable_liters == Decimal("0")
        assert RevenueEntry.objects.count() == 0
        assert pnl.liters == Decimal("12.000")
        assert pnl.saleable_liters == Decimal("12.000") - Decimal("12.000")
        assert pnl.discarded_liters == Decimal("12.000")
        assert pnl.discarded_value == Decimal("6.0000")
        assert pnl.revenue == Decimal("0")


@pytest.mark.django_db(transaction=True)
def test_milk_is_saleable_again_once_the_withdrawal_expires():
    tenant = create_tenant("postwithdraw")

    with tenant_context(tenant):
        farm, _, animal, _, medicine = seed_farm()
        started_at = timezone.now() - timedelta(days=10)

        record_treatment(
            farm=farm,
            animal=animal,
            diagnosis="Mastitis",
            started_at=started_at,
            input_=medicine,
            quantity=Decimal("10"),
        )
        today = timezone.localdate()
        result = register_milking_detailed(
            farm=farm,
            milking_date=today,
            shift=MilkingSession.Shift.TOTAL_DAY,
            records=[MilkRecord(animal=animal, liters=Decimal("12"))],
            unit_price=Decimal("0.50"),
        )
        pnl = get_operating_pnl(farm=farm, start_date=today, end_date=today)

        assert result.saleable_liters == Decimal("12")
        assert result.discarded_liters == Decimal("0")
        assert pnl.discarded_liters == Decimal("0")
        assert pnl.revenue == Decimal("6.0000")


@pytest.mark.django_db(transaction=True)
def test_offline_events_book_direct_expense_and_animal_sale():
    tenant = create_tenant("directev")

    with tenant_context(tenant):
        farm, _, animal, _, _ = seed_farm()
        today = timezone.localdate()

        expense_event = _action_message(
            farm=farm,
            event_type="finance.expense_recorded",
            payload={
                "amount": "150.00",
                "cost_type": "labor",
                "notes": "Jornal ordeno semana 4",
            },
            sequence=1,
        )
        sale_event = _action_message(
            farm=farm,
            event_type="herd.animal_sold",
            payload={
                "animal_id": str(animal.id),
                "amount": "820.00",
                "notes": "Venta a feria",
            },
            sequence=2,
        )

        assert process_action_event(expense_event).status == "acked"
        assert process_action_event(sale_event).status == "acked"
        # replaying the queue must not double-book
        assert process_action_event(expense_event).detail == "already_processed"

        animal.refresh_from_db()
        pnl = get_operating_pnl(farm=farm, start_date=today, end_date=today)
        trace = {row.source_event_id: row for row in get_event_trace(farm=farm)}

        assert CostAllocation.objects.filter(cost_type="labor").count() == 1
        assert animal.status == Animal.Status.SOLD
        assert pnl.costs == Decimal("150.0000")
        assert pnl.revenue == Decimal("820.0000")
        assert pnl.net_profit == Decimal("670.0000")
        # an animal sale is money, not liters
        assert pnl.liters == Decimal("0")
        assert trace[sale_event.event_id].liters == Decimal("0")
        assert trace[sale_event.event_id].revenue == Decimal("820.0000")


@pytest.mark.django_db(transaction=True)
def test_offline_receipt_and_adjustment_events_move_stock():
    tenant = create_tenant("stockev")

    with tenant_context(tenant):
        farm, _, _, feed, _ = seed_farm()

        receipt_event = _action_message(
            farm=farm,
            event_type="inventory.input_received",
            payload={
                "input_id": str(feed.id),
                "quantity": "5",
                "unit_cost": "18.50",
                "lot_code": "T1",
            },
            sequence=1,
        )
        adjustment_event = _action_message(
            farm=farm,
            event_type="inventory.stock_adjusted",
            payload={
                "input_id": str(feed.id),
                "quantity_delta": "-1",
                "reason": "Saco roto",
            },
            sequence=2,
        )

        assert process_action_event(receipt_event).status == "acked"
        assert process_action_event(adjustment_event).status == "acked"

        stock = StockLot.objects.get(farm=farm, input=feed)
        pnl = get_operating_pnl(farm=farm)

        assert stock.quantity_on_hand == Decimal("14.000")
        assert pnl.costs == Decimal("18.5000")
        assert CostAllocation.objects.get().cost_type == CostAllocation.CostType.SHRINKAGE


@pytest.mark.django_db(transaction=True)
def test_period_close_task_snapshots_discards_per_tenant():
    tenant = create_tenant("closetask")

    with tenant_context(tenant):
        farm, _, animal, _, medicine = seed_farm()
        today = timezone.localdate()

        record_treatment(
            farm=farm,
            animal=animal,
            diagnosis="Mastitis",
            started_at=timezone.now(),
            input_=medicine,
            quantity=Decimal("10"),
        )
        register_milking_detailed(
            farm=farm,
            milking_date=today,
            shift=MilkingSession.Shift.TOTAL_DAY,
            records=[MilkRecord(animal=animal, liters=Decimal("15"))],
            unit_price=Decimal("0.50"),
        )

    close_operating_periods(start_date=str(today), end_date=str(today))

    with tenant_context(tenant):
        snapshot = OperatingPeriodSnapshot.objects.get(
            scope=OperatingPeriodSnapshot.Scope.FARM,
            start_date=today,
            end_date=today,
        )

        assert snapshot.liters == Decimal("15.000")
        assert snapshot.discarded_liters == Decimal("15.000")
        assert snapshot.saleable_liters == Decimal("0.000")
        assert snapshot.discarded_value == Decimal("7.5000")
        assert snapshot.revenue == Decimal("0.0000")

    # re-running the close overwrites the same row instead of duplicating it
    close_operating_periods(start_date=str(today), end_date=str(today))

    with tenant_context(tenant):
        assert (
            OperatingPeriodSnapshot.objects.filter(
                scope=OperatingPeriodSnapshot.Scope.FARM
            ).count()
            == 1
        )


@pytest.mark.django_db(transaction=True)
def test_htmx_finance_screen_registers_a_direct_expense():
    tenant = create_tenant("expenseui")

    with tenant_context(tenant):
        farm, group, _, _, _ = seed_farm()
        farm_id, group_id = farm.id, group.id

    client = HttpClient(HTTP_HOST=f"{tenant.schema_name}.localhost")
    response = client.post(
        "/finanzas/gasto/",
        data={
            "farm": str(farm_id),
            "group": str(group_id),
            "cost_type": "labor",
            "amount": "75.50",
            "notes": "Jornal ordeno",
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert "Gasto operativo registrado" in response.content.decode()
    with tenant_context(tenant):
        allocation = CostAllocation.objects.get()
        assert allocation.cost_type == "labor"
        assert allocation.amount == Decimal("75.5000")
        assert allocation.group_id == group_id


@pytest.mark.django_db(transaction=True)
def test_htmx_master_data_registers_an_input_receipt():
    tenant = create_tenant("receiptui")

    with tenant_context(tenant):
        farm, _, _, feed, _ = seed_farm()
        farm_id, feed_id = farm.id, feed.id

    client = HttpClient(HTTP_HOST=f"{tenant.schema_name}.localhost")
    response = client.post(
        "/datos/stock/recepcion/",
        data={
            "farm": str(farm_id),
            "input": str(feed_id),
            "quantity": "4",
            "unit_cost": "19.00",
            "lot_code": "COMPRA-1",
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    with tenant_context(tenant):
        lot = StockLot.objects.get(lot_code="COMPRA-1")
        assert lot.quantity_on_hand == Decimal("4.000")
        assert InventoryMovement.objects.filter(
            movement_type=InventoryMovement.MovementType.IN
        ).count() == 1
