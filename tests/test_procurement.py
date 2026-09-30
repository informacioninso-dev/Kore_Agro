from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context, tenant_context

from apps.configuration.models import OrganizationCapability
from apps.finance.models import CostAllocation
from apps.inventory.models import InventoryMovement, StockLot
from apps.parties.models import Counterparty
from apps.procurement.models import GoodsReceipt, PurchaseOrder, PurchaseOrderLine
from apps.procurement.services import receive_purchase_line
from tests.factories import authenticated_manager_client, create_tenant, seed_farm


def _supplier(**overrides) -> Counterparty:
    values = {
        "legal_name": "Proveedor de prueba S.A.",
        "identification_number": "1790000000001",
        "is_supplier": True,
    }
    values.update(overrides)
    return Counterparty.objects.create(**values)


@pytest.mark.django_db(transaction=True)
def test_purchase_receipt_updates_stock_and_keeps_cost_out_of_pnl():
    tenant = create_tenant("purchasecost")
    with tenant_context(tenant):
        farm, _, _, feed, _ = seed_farm()
        supplier = _supplier()
        order = PurchaseOrder.objects.create(
            farm=farm,
            supplier=supplier,
            number="OC-COST-001",
            status=PurchaseOrder.Status.ORDERED,
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=order,
            input=feed,
            quantity_ordered=Decimal("4"),
            unit_cost=Decimal("20"),
        )

        result = receive_purchase_line(
            order_line=line,
            quantity=Decimal("4"),
            lot_code="T1",
            supplier_document="FAC-100",
        )

        order.refresh_from_db()
        stock = StockLot.objects.get(farm=farm, input=feed, lot_code="T1")
        movement = InventoryMovement.objects.get(pk=result.line.inventory_movement_id)
        assert order.status == PurchaseOrder.Status.RECEIVED
        assert stock.quantity_on_hand == Decimal("14.000")
        assert stock.unit_cost == Decimal("18.9286")
        assert movement.total_cost == Decimal("80.0000")
        assert result.receipt.supplier_document == "FAC-100"
        assert CostAllocation.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_partial_receipt_rejects_quantity_above_remaining_balance():
    tenant = create_tenant("purchasepartial")
    with tenant_context(tenant):
        farm, _, _, feed, _ = seed_farm()
        supplier = _supplier(identification_number="1790000000002")
        order = PurchaseOrder.objects.create(
            farm=farm,
            supplier=supplier,
            number="OC-PART-001",
            status=PurchaseOrder.Status.ORDERED,
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=order,
            input=feed,
            quantity_ordered=Decimal("10"),
            unit_cost=Decimal("19"),
        )

        receive_purchase_line(order_line=line, quantity=Decimal("3"), lot_code="PART-A")
        order.refresh_from_db()
        line.refresh_from_db()
        assert order.status == PurchaseOrder.Status.PARTIAL
        assert line.remaining_quantity == Decimal("7.000")

        with pytest.raises(ValidationError, match="supera el saldo"):
            receive_purchase_line(order_line=line, quantity=Decimal("8"), lot_code="PART-B")

        assert GoodsReceipt.objects.count() == 1
        assert InventoryMovement.objects.filter(notes__startswith="Compra OC-PART-001").count() == 1


@pytest.mark.django_db(transaction=True)
def test_counterparty_requires_at_least_one_role():
    tenant = create_tenant("partyrole")
    with tenant_context(tenant):
        with pytest.raises(ValidationError, match="al menos un rol"):
            Counterparty.objects.create(legal_name="Sin rol")


@pytest.mark.django_db(transaction=True)
def test_manager_completes_supplier_order_and_receipt_web_flow():
    tenant = create_tenant("purchaseweb")
    with tenant_context(tenant):
        farm, _, _, feed, _ = seed_farm()
    client = authenticated_manager_client(tenant)
    today = timezone.localdate().isoformat()

    supplier_response = client.post(
        "/compras/proveedores/crear/",
        {
            "farm": str(farm.id),
            "legal_name": "Nutricion del Campo Cia. Ltda.",
            "trade_name": "NutriCampo",
            "identification_type": Counterparty.IdentificationType.RUC,
            "identification_number": "1792222222001",
            "is_supplier": "on",
            "email": "compras@nutricampo.example",
            "phone": "022222222",
            "province": "Pichincha",
            "city": "Quito",
            "address": "Via principal",
            "payment_terms_days": "15",
            "notes": "",
        },
    )
    assert supplier_response.status_code == 200
    assert "Proveedor NutriCampo creado" in supplier_response.content.decode()
    with tenant_context(tenant):
        supplier = Counterparty.objects.get(identification_number="1792222222001")

    order_response = client.post(
        "/compras/ordenes/crear/",
        {
            "farm": str(farm.id),
            "number": "OC-WEB-001",
            "supplier": str(supplier.id),
            "ordered_on": today,
            "expected_on": today,
            "notes": "Compra web",
        },
    )
    assert order_response.status_code == 200
    with tenant_context(tenant):
        order = PurchaseOrder.objects.get(number="OC-WEB-001")

    line_response = client.post(
        "/compras/ordenes/lineas/crear/",
        {
            "farm": str(farm.id),
            "purchase_order": str(order.id),
            "input": str(feed.id),
            "quantity": "5",
            "unit_cost": "17.25",
            "tax_rate": "0",
        },
    )
    assert line_response.status_code == 200
    with tenant_context(tenant):
        line = PurchaseOrderLine.objects.get(purchase_order=order)

    place_response = client.post(
        "/compras/ordenes/accion/",
        {
            "farm": str(farm.id),
            "purchase_order": str(order.id),
            "action": "place",
        },
    )
    assert place_response.status_code == 200

    receipt_response = client.post(
        "/compras/recepciones/crear/",
        {
            "farm": str(farm.id),
            "order_line": str(line.id),
            "quantity": "5",
            "received_at": f"{today}T09:30",
            "lot_code": "WEB-01",
            "expires_on": "",
            "supplier_document": "FAC-WEB-01",
            "notes": "Entrega completa",
        },
    )
    assert receipt_response.status_code == 200
    assert "registrada en OC-WEB-001 e inventario" in receipt_response.content.decode()
    with tenant_context(tenant):
        order.refresh_from_db()
        assert order.status == PurchaseOrder.Status.RECEIVED
        assert StockLot.objects.get(farm=farm, input=feed, lot_code="WEB-01").quantity_on_hand == 5


@pytest.mark.django_db(transaction=True)
def test_procurement_route_requires_capability():
    tenant = create_tenant("purchaseaccess")
    client = authenticated_manager_client(tenant)
    with schema_context(get_public_schema_name()):
        assignment = OrganizationCapability.objects.get(
            organization=tenant,
            capability__code="procurement",
        )
        assignment.status = OrganizationCapability.Status.SUSPENDED
        assignment.save(update_fields=["status"])

    response = client.get("/compras/")
    home_response = client.get("/")

    assert response.status_code == 403
    assert "Proveedores y compras" not in home_response.content.decode()
