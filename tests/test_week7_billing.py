from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.billing.models import MilkInvoice
from apps.billing.services import (
    SRIConfigurationError,
    create_draft_milk_invoice,
    request_sri_submission,
)
from apps.milk.models import MilkingSession
from apps.milk.services import MilkRecord, register_milking
from tests.factories import create_tenant, seed_farm


@pytest.mark.django_db(transaction=True)
def test_milk_invoice_uses_saleable_milk_revenue_once_per_period():
    tenant = create_tenant("billinginvoice")

    with tenant_context(tenant):
        farm, _, animal, _, _ = seed_farm()
        today = timezone.localdate()
        register_milking(
            farm=farm,
            milking_date=today,
            shift=MilkingSession.Shift.TOTAL_DAY,
            records=[MilkRecord(animal=animal, liters=Decimal("10"))],
            unit_price=Decimal("0.50"),
            source_event_id=uuid4(),
        )

        invoice = create_draft_milk_invoice(
            farm=farm,
            buyer_ruc="1799999999001",
            buyer_name="Planta Demo",
            period_start=today,
            period_end=today,
        )

        assert invoice.status == MilkInvoice.Status.DRAFT
        assert invoice.liters == Decimal("10")
        assert invoice.total == Decimal("5.0000")
        with pytest.raises(ValidationError, match="Ya existe una factura activa"):
            create_draft_milk_invoice(
                farm=farm,
                buyer_ruc="1799999999001",
                buyer_name="Planta Demo",
                period_start=today,
                period_end=today,
            )


@pytest.mark.django_db(transaction=True)
def test_invoice_without_sales_cannot_be_created_or_sent_without_sri_adapter():
    tenant = create_tenant("billingguard")

    with tenant_context(tenant):
        farm, _, _, _, _ = seed_farm()
        today = timezone.localdate()
        with pytest.raises(ValidationError, match="No hay ventas de leche"):
            create_draft_milk_invoice(
                farm=farm,
                buyer_ruc="1799999999001",
                buyer_name="Planta Demo",
                period_start=today - timedelta(days=1),
                period_end=today,
            )

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
        with pytest.raises(SRIConfigurationError):
            request_sri_submission(invoice)

        invoice.refresh_from_db()
        assert invoice.status == MilkInvoice.Status.DRAFT
