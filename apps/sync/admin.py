from django.contrib import admin

from .models import IncomingEvent


@admin.register(IncomingEvent)
class IncomingEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_id",
        "event_type",
        "device_id",
        "client_sequence",
        "status",
        "occurred_at",
    )
    search_fields = ("event_id", "device_id", "event_type", "error_message")
    list_filter = ("status", "event_type", "schema_version")
    readonly_fields = ("event_id", "payload", "error_message", "processed_at")
