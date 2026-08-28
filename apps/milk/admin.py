from django.contrib import admin

from .models import MilkingSession, MilkYield


class MilkYieldInline(admin.TabularInline):
    model = MilkYield
    extra = 0


@admin.register(MilkingSession)
class MilkingSessionAdmin(admin.ModelAdmin):
    list_display = ("farm", "milking_date", "shift", "source_event_id")
    list_filter = ("farm", "shift", "milking_date")
    inlines = [MilkYieldInline]


@admin.register(MilkYield)
class MilkYieldAdmin(admin.ModelAdmin):
    list_display = ("session", "animal", "group", "liters")
    search_fields = ("animal__tag", "group__name")
    list_filter = ("farm",)

