from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.finance.models import RevenueEntry
from apps.herd.models import Farm

from .models import MilkInvoice


def create_draft_milk_invoice(
    *,
    farm: Farm,
    buyer_ruc: str,
    buyer_name: str,
    period_start,
    period_end,
) -> MilkInvoice:
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

