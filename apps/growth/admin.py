from django.contrib import admin

from .models import WeightRecord


@admin.register(WeightRecord)
class WeightRecordAdmin(admin.ModelAdmin):
    list_display = (
        "animal",
        "farm",
        "group",
        "weighed_on",
        "weight_kg",
        "body_condition_score",
        "operator",
    )
    list_filter = ("farm", "group", "weighed_on")
    search_fields = ("animal__tag", "animal__name", "scale_identifier")
    date_hierarchy = "weighed_on"
