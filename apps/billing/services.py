from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone

from apps.finance.models import RevenueEntry
from apps.herd.models import Farm

from .models import MilkInvoice


class SRIConfigurationError(ValidationError):
    pass


def create_draft_milk_invoice(
    *,
    farm: Farm,
    buyer_ruc: str,
    buyer_name: str,
    period_start,
    period_end,
) -> MilkInvoice:
    if period_end < period_start:
        raise ValidationError("El fin del periodo no puede ser anterior al inicio.")
    if MilkInvoice.objects.filter(
        farm=farm,
        buyer_ruc=buyer_ruc,
        period_start=period_start,
        period_end=period_end,
    ).exclude(status=MilkInvoice.Status.REJECTED).exists():
        raise ValidationError("Ya existe una factura activa para este comprador y periodo.")

    revenue = RevenueEntry.objects.filter(
        farm=farm,
        revenue_type=RevenueEntry.RevenueType.MILK,
        revenue_date__gte=period_start,
        revenue_date__lte=period_end,
    ).aggregate(
        liters=Sum("quantity"),
        subtotal=Sum("gross_amount"),
    )
    liters = revenue["liters"] or Decimal("0")
    subtotal = revenue["subtotal"] or Decimal("0")
    if liters <= 0 or subtotal <= 0:
        raise ValidationError("No hay ventas de leche facturables para el periodo seleccionado.")
    unit_price = subtotal / liters if liters else Decimal("0")

    return MilkInvoice.objects.create(
        farm=farm,
        issue_date=timezone.localdate(),
        buyer_ruc=buyer_ruc,
        buyer_name=buyer_name,
        period_start=period_start,
        period_end=period_end,
        liters=liters,
        unit_price=unit_price,
        subtotal=subtotal,
        tax_amount=Decimal("0"),
        total=subtotal,
    )


def request_sri_submission(invoice: MilkInvoice) -> None:
    """Validate that a certified SRI connector is configured before submission.

    Legal electronic invoicing cannot be simulated: without the taxpayer's
    certificate and configured adapter, the invoice remains a draft.
    """
    from django.conf import settings
    from django.utils.module_loading import import_string

    if not getattr(settings, "SRI_ADAPTER_CLASS", ""):
        raise SRIConfigurationError(
            "No hay conector SRI configurado. Carga el certificado y configura el adaptador."
        )

    adapter = import_string(settings.SRI_ADAPTER_CLASS)()
    response = adapter.submit_milk_invoice(invoice)
    invoice.status = MilkInvoice.Status.SUBMITTED
    invoice.access_key = response.get("access_key", invoice.access_key)
    invoice.sri_response = response
    invoice.save(update_fields=["status", "access_key", "sri_response", "updated_at"])

