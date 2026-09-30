from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context, tenant_context

from apps.billing.models import MilkInvoice
from apps.billing.tasks import submit_milk_invoice_to_sri
from apps.milk.models import MilkYield
from apps.sync.models import IncomingEvent
from apps.sync.tasks import process_incoming_event
from tests.factories import create_tenant, seed_farm


@pytest.mark.django_db(transaction=True)
def test_sync_task_switches_to_the_requested_tenant():
    tenant = create_tenant("synctask")
    event_id = uuid4()

    with tenant_context(tenant):
        farm, _, animal, _, _ = seed_farm()
        IncomingEvent.objects.create(
            event_id=event_id,
            tenant_id=tenant.id,
            device_id=uuid4(),
            client_sequence=1,
            event_type="milk.milking_recorded",
            occurred_at=timezone.now(),
            payload={
                "farm_id": str(farm.id),
                "records": [{"animal_id": str(animal.id), "liters": "7.5"}],
            },
        )

    with schema_context(get_public_schema_name()):
        result = process_incoming_event.run(tenant.schema_name, str(event_id))

    assert result["status"] == "acked"
    with tenant_context(tenant):
        assert IncomingEvent.objects.get(event_id=event_id).status == IncomingEvent.Status.PROCESSED
        assert MilkYield.objects.get().liters == Decimal("7.500")


@pytest.mark.django_db(transaction=True)
def test_billing_task_switches_to_the_requested_tenant():
    tenant = create_tenant("billingtask")

    with tenant_context(tenant):
        farm, _, _, _, _ = seed_farm()
        today = timezone.localdate()
        invoice = MilkInvoice.objects.create(
            farm=farm,
            buyer_ruc="1799999999001",
            buyer_name="Planta Demo",
            period_start=today,
            period_end=today,
            liters=Decimal("1"),
            unit_price=Decimal("0.50"),
            subtotal=Decimal("0.50"),
            total=Decimal("0.50"),
        )

    def authorize(invoice_to_submit):
        invoice_to_submit.status = MilkInvoice.Status.AUTHORIZED
        invoice_to_submit.save(update_fields=["status", "updated_at"])

    with (
        schema_context(get_public_schema_name()),
        patch("apps.billing.tasks.request_sri_submission", side_effect=authorize) as submit,
    ):
        result = submit_milk_invoice_to_sri.run(tenant.schema_name, str(invoice.id))

    assert result == {"invoice_id": str(invoice.id), "status": MilkInvoice.Status.AUTHORIZED}
    submit.assert_called_once()
    with tenant_context(tenant):
        assert MilkInvoice.objects.get(id=invoice.id).status == MilkInvoice.Status.AUTHORIZED
