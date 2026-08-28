from django.contrib import admin

from .models import ReproductionEvent


@admin.register(ReproductionEvent)
class ReproductionEventAdmin(admin.ModelAdmin):
    list_display = ("animal", "event_type", "occurred_on", "service_type", "pregnancy_positive")
    search_fields = ("animal__tag", "sire_identifier", "calf_tag")
    list_filter = ("event_type", "service_type", "pregnancy_positive", "farm")

