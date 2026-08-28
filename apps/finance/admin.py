from django.contrib import admin

from .models import CostAllocation, RevenueEntry


@admin.register(RevenueEntry)
class RevenueEntryAdmin(admin.ModelAdmin):
    list_display = (
        "revenue_type",
        "farm",
        "group",
        "animal",
        "quantity",
        "gross_amount",
        "revenue_date",
    )
    search_fields = ("notes", "animal__tag", "group__name")
    list_filter = ("revenue_type", "farm", "revenue_date")


@admin.register(CostAllocation)
class CostAllocationAdmin(admin.ModelAdmin):
    list_display = ("cost_type", "farm", "group", "animal", "amount", "cost_date")
    search_fields = ("notes", "animal__tag", "group__name")
    list_filter = ("cost_type", "farm", "cost_date")
