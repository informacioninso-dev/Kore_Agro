from django.contrib import admin

from .models import AnimalMovementGuide, MilkInvoice


@admin.register(MilkInvoice)
class MilkInvoiceAdmin(admin.ModelAdmin):
    list_display = ("buyer_name", "buyer_ruc", "issue_date", "liters", "total", "status")
    search_fields = ("buyer_name", "buyer_ruc", "access_key", "authorization_number")
    list_filter = ("status", "issue_date", "farm")


@admin.register(AnimalMovementGuide)
class AnimalMovementGuideAdmin(admin.ModelAdmin):
    list_display = ("origin", "destination", "issue_date", "reason", "status")
    search_fields = ("origin", "destination", "access_key", "authorization_number")
    list_filter = ("status", "issue_date", "farm")
    filter_horizontal = ("animals",)

