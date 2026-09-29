from django.contrib import admin

from .models import GrazingPeriod, Paddock


@admin.register(Paddock)
class PaddockAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "farm",
        "area_hectares",
        "forage_type",
        "rest_target_days",
        "is_active",
    )
    list_filter = ("farm", "forage_type", "is_active")
    search_fields = ("name", "code", "farm__name")


@admin.register(GrazingPeriod)
class GrazingPeriodAdmin(admin.ModelAdmin):
    list_display = (
        "paddock",
        "group",
        "started_on",
        "planned_end_on",
        "ended_on",
        "head_count",
    )
    list_filter = ("farm", "started_on", "ended_on")
    search_fields = ("paddock__name", "group__name")
    date_hierarchy = "started_on"
