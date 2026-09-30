from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.identity.access import ROLE_FIELD_WORKER, ensure_role_groups
from apps.identity.models import FieldAssignment
from apps.parties.models import Counterparty
from apps.procurement.models import GoodsReceipt, PurchaseOrder, PurchaseOrderLine
from tests.factories import authenticated_client, create_tenant, seed_farm


@pytest.mark.django_db(transaction=True)
def test_field_worker_receives_pending_purchase_offline_once():
    tenant = create_tenant("purchaseoffline")
    with tenant_context(tenant):
        ensure_role_groups()
        user = get_user_model().objects.create_user(username="receiver", password="safe-password")
        user.groups.add(Group.objects.get(name=ROLE_FIELD_WORKER))
        farm, _, _, feed, _ = seed_farm()
        FieldAssignment.objects.create(user=user, farm=farm)
        supplier = Counterparty.objects.create(
            legal_name="Proveedor Offline",
            identification_number="1794444444001",
            is_supplier=True,
        )
        order = PurchaseOrder.objects.create(
            farm=farm,
            supplier=supplier,
            number="OC-OFF-001",
            status=PurchaseOrder.Status.ORDERED,
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=order,
            input=feed,
            quantity_ordered=Decimal("6"),
            unit_cost=Decimal("18"),
        )
    client = authenticated_client(tenant, user)
    device_id = uuid4()

    bootstrap = client.get(
        "/api/field/bootstrap",
        HTTP_X_KORE_DEVICE_ID=str(device_id),
    )
    assert bootstrap.status_code == 200
    assert bootstrap.json()["purchase_lines"][0]["order_number"] == "OC-OFF-001"

    event_id = uuid4()
    payload = {
        "events": [
            {
                "event_id": str(event_id),
                "device_id": str(device_id),
                "actor_id": None,
                "tenant_id": None,
                "occurred_at": timezone.now().isoformat(),
                "event_type": "procurement.purchase_received",
                "payload": {
                    "farm_id": str(farm.id),
                    "order_line_id": str(line.id),
                    "quantity": "6",
                    "lot_code": "OFF-01",
                    "supplier_document": "FAC-OFF-01",
                },
                "client_sequence": 1,
                "schema_version": 1,
            }
        ]
    }
    first = client.post(
        "/api/sync/events",
        data=payload,
        content_type="application/json",
        HTTP_X_KORE_DEVICE_ID=str(device_id),
    )
    second = client.post(
        "/api/sync/events",
        data=payload,
        content_type="application/json",
        HTTP_X_KORE_DEVICE_ID=str(device_id),
    )

    assert first.json()["results"][0]["status"] == "acked"
    assert second.json()["results"][0]["detail"] == "already_processed"
    with tenant_context(tenant):
        receipt = GoodsReceipt.objects.get(source_event_id=event_id)
        assert receipt.purchase_order_id == order.id
        assert receipt.lines.get().quantity == Decimal("6.000")
