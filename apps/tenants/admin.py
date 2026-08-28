from django.contrib import admin

from .models import Client, Domain


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "schema_name", "ruc", "province", "on_trial", "paid_until")
    search_fields = ("name", "schema_name", "ruc")
    list_filter = ("on_trial", "province")


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("domain", "tenant", "is_primary")
    search_fields = ("domain", "tenant__name")

