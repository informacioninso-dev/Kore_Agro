import pytest
from django_tenants.utils import tenant_context

from apps.audit.models import AuditEvent
from apps.parties.models import Counterparty
from tests.factories import authenticated_manager_client, create_tenant, seed_farm


@pytest.mark.django_db(transaction=True)
def test_web_change_records_actor_route_and_field_diff():
    tenant = create_tenant("auditactor")
    with tenant_context(tenant):
        farm, _, _, _, _ = seed_farm()
    client = authenticated_manager_client(tenant)

    response = client.post(
        "/compras/proveedores/crear/",
        {
            "farm": str(farm.id),
            "legal_name": "Proveedor Auditado S.A.",
            "trade_name": "Auditado",
            "identification_type": "ruc",
            "identification_number": "1793333333001",
            "is_supplier": "on",
            "email": "",
            "phone": "",
            "province": "",
            "city": "",
            "address": "",
            "payment_terms_days": "0",
            "notes": "",
        },
    )

    assert response.status_code == 200
    with tenant_context(tenant):
        supplier = Counterparty.objects.get(identification_number="1793333333001")
        event = AuditEvent.objects.get(
            model_label="parties.counterparty",
            object_id=str(supplier.id),
            action=AuditEvent.Action.CREATE,
        )
        assert event.actor_username.startswith("manager-")
        assert event.request_method == "POST"
        assert event.request_path == "/compras/proveedores/crear/"
        assert event.changes["snapshot"]["legal_name"] == "Proveedor Auditado S.A."


@pytest.mark.django_db(transaction=True)
def test_audit_dashboard_requires_permission_and_lists_events():
    tenant = create_tenant("auditdashboard")
    client = authenticated_manager_client(tenant)
    with tenant_context(tenant):
        Counterparty.objects.create(legal_name="Registro visible", is_supplier=True)

    response = client.get("/auditoria/")

    assert response.status_code == 200
    assert "Registro visible" in response.content.decode()
