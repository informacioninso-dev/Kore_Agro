from django.contrib import admin

from .models import FieldAssignment, FieldDevice


@admin.register(FieldAssignment)
class FieldAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "farm", "is_active")
    search_fields = ("user__username", "user__first_name", "user__last_name", "farm__name")
    list_filter = ("is_active", "farm")


@admin.register(FieldDevice)
class FieldDeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "device_uuid", "assigned_to", "is_trusted", "last_seen_at")
    search_fields = ("name", "device_uuid")
    list_filter = ("is_trusted",)
