from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.finance.models import RevenueEntry
from apps.inventory.models import InventoryMovement, StockLot
from apps.milk.models import MilkYield
from apps.sync.models import IncomingEvent
from apps.sync.services import ActionEventMessage, process_action_event
from tests.factories import create_tenant, seed_farm


def _message(*, device_id, sequence, event_type, payload, event_id=None, schema_version=1):
    return ActionEventMessage(
        event_id=event_id or uuid4(),
        tenant_id=None,
        device_id=device_id,
        actor_id=None,
        client_sequence=sequence,
        schema_version=schema_version,
        event_type=event_type,
        occurred_at=timezone.now(),
        payload=payload,
    )


@pytest.mark.django_db(transaction=True)
def test_reused_event_id_with_changed_content_is_a_conflict():
    tenant = create_tenant("sync_event_id")

    with tenant_context(tenant):
        farm, _, animal, _, _ = seed_farm()
        message = _message(
            device_id=uuid4(),
            sequence=1,
            event_type="milk.milking_recorded",
            payload={
                "farm_id": str(farm.id),
                "records": [{"animal_id": str(animal.id), "liters": "10"}],
            },
        )

        first = process_action_event(message)
        changed = replace(
            message,
            payload={
                "farm_id": str(farm.id),
                "records": [{"animal_id": str(animal.id), "liters": "99"}],
            },
        )
        second = process_action_event(changed)

        assert first.status == "acked"
        assert second.status == "conflict"
        assert "event_id was already used" in second.detail
        assert IncomingEvent.objects.get().status == IncomingEvent.Status.PROCESSED
        assert MilkYield.objects.get().liters == Decimal("10.000")
        assert RevenueEntry.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_reused_device_sequence_is_recorded_as_a_conflict():
    tenant = create_tenant("sync_sequence")

    with tenant_context(tenant):
        farm, _, animal, feed, _ = seed_farm()
        device_id = uuid4()
        milk = _message(
            device_id=device_id,
            sequence=7,
            event_type="milk.milking_recorded",
            payload={
                "farm_id": str(farm.id),
                "records": [{"animal_id": str(animal.id), "liters": "8"}],
            },
        )
        consumption = _message(
            device_id=device_id,
            sequence=7,
            event_type="inventory.input_consumed",
            payload={
                "farm_id": str(farm.id),
                "input_id": str(feed.id),
                "quantity": "1",
            },
        )

        assert process_action_event(milk).status == "acked"
        result = process_action_event(consumption)

        assert result.status == "conflict"
        assert str(milk.event_id) in result.detail
        conflict = IncomingEvent.objects.get(event_id=consumption.event_id)
        assert conflict.status == IncomingEvent.Status.CONFLICT
        assert conflict.error_code == "client_sequence_reused"
        assert InventoryMovement.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_failed_event_can_be_retried_without_partial_stock_writes():
    tenant = create_tenant("sync_retry")

    with tenant_context(tenant):
        farm, _, _, feed, _ = seed_farm()
        message = _message(
            device_id=uuid4(),
            sequence=1,
            event_type="inventory.input_consumed",
            payload={
                "farm_id": str(farm.id),
                "input_id": str(feed.id),
                "quantity": "12",
            },
        )

        first = process_action_event(message)
        stock = StockLot.objects.get(farm=farm, input=feed)

        assert first.status == "failed"
        assert stock.quantity_on_hand == Decimal("10.000")
        assert InventoryMovement.objects.count() == 0

        stock.quantity_on_hand = Decimal("20")
        stock.save(update_fields=["quantity_on_hand", "updated_at"])
        second = process_action_event(message)

        assert second.status == "acked"
        assert IncomingEvent.objects.get().status == IncomingEvent.Status.PROCESSED
        assert StockLot.objects.get(farm=farm, input=feed).quantity_on_hand == Decimal("8.000")
        assert InventoryMovement.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_invalid_payload_is_failed_before_domain_writes():
    tenant = create_tenant("sync_validation")

    with tenant_context(tenant):
        farm, _, animal, _, _ = seed_farm()
        message = _message(
            device_id=uuid4(),
            sequence=1,
            event_type="milk.milking_recorded",
            payload={
                "farm_id": str(farm.id),
                "milking_date": "not-a-date",
                "records": [{"animal_id": str(animal.id), "liters": "10"}],
            },
        )

        result = process_action_event(message)

        assert result.status == "failed"
        assert "Invalid date" in result.detail
        event = IncomingEvent.objects.get(event_id=message.event_id)
        assert event.status == IncomingEvent.Status.FAILED
        assert MilkYield.objects.count() == 0
        assert RevenueEntry.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_unsupported_schema_version_is_failed_without_dispatch():
    tenant = create_tenant("sync_schema")

    with tenant_context(tenant):
        farm, _, animal, _, _ = seed_farm()
        message = _message(
            device_id=uuid4(),
            sequence=1,
            schema_version=2,
            event_type="milk.milking_recorded",
            payload={
                "farm_id": str(farm.id),
                "records": [{"animal_id": str(animal.id), "liters": "10"}],
            },
        )

        result = process_action_event(message)

        assert result.status == "failed"
        assert "Unsupported schema_version" in result.detail
        assert IncomingEvent.objects.get().status == IncomingEvent.Status.FAILED
        assert MilkYield.objects.count() == 0
