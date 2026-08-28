from django.contrib import admin

from .models import MilkWithdrawal, Treatment


@admin.register(Treatment)
class TreatmentAdmin(admin.ModelAdmin):
    list_display = ("animal", "diagnosis", "input", "started_at", "milk_withdrawal_until")
    search_fields = ("animal__tag", "diagnosis", "notes")
    list_filter = ("farm", "input__category", "started_at")


@admin.register(MilkWithdrawal)
class MilkWithdrawalAdmin(admin.ModelAdmin):
    list_display = ("animal", "reason", "starts_at", "ends_at", "is_active_now")
    search_fields = ("animal__tag", "reason")
    list_filter = ("farm", "ends_at")

