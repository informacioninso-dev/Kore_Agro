from django.contrib import admin

from .models import Input, InventoryMovement, StockLot


@admin.register(Input)
class InputAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "unit", "default_unit_cost", "milk_withdrawal_hours")
    search_fields = ("name", "sku")
    list_filter = ("category", "unit", "is_active")


@admin.register(StockLot)
class StockLotAdmin(admin.ModelAdmin):
    list_display = ("input", "farm", "lot_code", "quantity_on_hand", "unit_cost", "expires_on")
    search_fields = ("input__name", "lot_code")
    list_filter = ("farm", "input__category")


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = ("input", "movement_type", "quantity", "total_cost", "farm", "occurred_at")
    search_fields = ("input__name", "notes")
    list_filter = ("movement_type", "input__category", "farm")

