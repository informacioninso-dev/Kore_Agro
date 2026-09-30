from django.contrib import admin

from .models import Counterparty


@admin.register(Counterparty)
class CounterpartyAdmin(admin.ModelAdmin):
    list_display = (
        "legal_name",
        "identification_number",
        "is_supplier",
        "is_producer",
        "is_customer",
        "is_active",
    )
    list_filter = ("is_supplier", "is_producer", "is_customer", "is_carrier", "is_active")
    search_fields = ("legal_name", "trade_name", "identification_number", "email", "phone")
