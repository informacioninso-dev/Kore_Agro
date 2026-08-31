from uuid import uuid4

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.sync.models import IncomingEvent
from apps.sync.services import ActionEventMessage, process_action_event, process_action_queue
from tests.factories import create_tenant, seed_farm


def _event(*, farm, device_id, sequence, event_id=None, quantity="1"):
    return ActionEventMessage(
        event_id=event_id or uuid4(),
        tenant_id=None,
        device_id=device_id,
        actor_id=None,
        client_sequence=sequence,
        schema_version=1,
        event_type="inventory.input_consumed",
        occurred_at=timezone.now(),
        payload={
            "farm_id": str(farm.id),
            "input_id": str(farm.inputs.first().id),
            "quantity": quantity,
        },
    )


@pytest.mark.django_db(transaction=True)
def test_reused_event_id_with_changed_payload_is_a_conflict():
    tenant = create_tenant("eventreuse")

    with tenant_context(tenant):
        farm, _, _, feed, _ = seed_farm()
        event_id = uuid4()
        first = ActionEventMessage(
            event_id=event_id,
            tenant_id=None,
            device_id=uuid4(),
            actor_id=None,
            client_sequence=1,
            schema_version=1,
            event_type="inventory.input_consumed",
            occurred_at=timezone.now(),
            payload={"farm_id": str(farm.id), "input_id": str(feed.id), "quantity": "1"},
        )
        changed = ActionEventMessage(
            event_id=event_id,
            tenant_id=None,
            device_id=first.device_id,
            actor_id=None,
            client_sequence=1,
            schema_version=1,
            event_type="inventory.input_consumed",
            occurred_at=first.occurred_at,
            payload={"farm_id": str(farm.id), "input_id": str(feed.id), "quantity": "2"},
        )

        assert process_action_event(first).status == "acked"
        result = process_action_event(changed)

        assert result.status == "conflict"
        assert IncomingEvent.objects.get(event_id=event_id).status == IncomingEvent.Status.PROCESSED


@pytest.mark.django_db(transaction=True)
def test_duplicate_device_sequence_is_a_conflict():
    tenant = create_tenant("sequenceconflict")

    with tenant_context(tenant):
        farm, _, _, feed, _ = seed_farm()
        device_id = uuid4()
        first = ActionEventMessage(
            event_id=uuid4(),
            tenant_id=None,
            device_id=device_id,
            actor_id=None,
            client_sequence=1,
            schema_version=1,
            event_type="inventory.input_consumed",
            occurred_at=timezone.now(),
            payload={"farm_id": str(farm.id), "input_id": str(feed.id), "quantity": "1"},
        )
        duplicate_sequence = ActionEventMessage(
            event_id=uuid4(),
            tenant_id=None,
            device_id=device_id,
            actor_id=None,
            client_sequence=1,
            schema_version=1,
            event_type="inventory.input_consumed",
            occurred_at=timezone.now(),
            payload={"farm_id": str(farm.id), "input_id": str(feed.id), "quantity": "1"},
        )

        assert process_action_event(first).status == "acked"
        result = process_action_event(duplicate_sequence)

        assert result.status == "conflict"
        assert IncomingEvent.objects.get(event_id=duplicate_sequence.event_id).status == "conflict"


@pytest.mark.django_db(transaction=True)
def test_queue_blocks_later_events_after_a_recoverable_failure():
    tenant = create_tenant("queueblock")

    with tenant_context(tenant):
        farm, _, _, feed, _ = seed_farm()
        device_id = uuid4()
        first = ActionEventMessage(
            event_id=uuid4(),
            tenant_id=None,
            device_id=device_id,
            actor_id=None,
            client_sequence=1,
            schema_version=1,
            event_type="inventory.input_consumed",
            occurred_at=timezone.now(),
            payload={"farm_id": str(farm.id), "input_id": str(feed.id), "quantity": "999"},
        )
        second = ActionEventMessage(
            event_id=uuid4(),
            tenant_id=None,
            device_id=device_id,
            actor_id=None,
            client_sequence=2,
            schema_version=1,
            event_type="inventory.input_consumed",
            occurred_at=timezone.now(),
            payload={"farm_id": str(farm.id), "input_id": str(feed.id), "quantity": "1"},
        )

        results = process_action_queue([second, first])

        assert results[0].status == "failed"
        assert results[0].retryable is True
        assert results[1].status == "blocked"
        assert IncomingEvent.objects.filter(event_id=second.event_id).exists() is False
