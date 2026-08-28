from django.contrib import admin

from .models import FieldDevice


@admin.register(FieldDevice)
class FieldDeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "device_uuid", "assigned_to", "is_trusted", "last_seen_at")
    search_fields = ("name", "device_uuid")
    list_filter = ("is_trusted",)

