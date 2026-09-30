from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor_username", "action", "model_label", "object_repr")
    list_filter = ("action", "model_label", "created_at")
    search_fields = ("actor_username", "object_id", "object_repr", "request_path")
    readonly_fields = [field.name for field in AuditEvent._meta.fields]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
