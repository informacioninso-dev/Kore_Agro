from django.contrib import admin

from .models import (
    CapabilityDefinition,
    OrganizationCapability,
    OrganizationProfile,
    ProfileDefinition,
)


@admin.register(ProfileDefinition)
class ProfileDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name", "code")


@admin.register(CapabilityDefinition)
class CapabilityDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "category", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "code")
    filter_horizontal = ("compatible_profiles", "dependencies")


@admin.register(OrganizationProfile)
class OrganizationProfileAdmin(admin.ModelAdmin):
    list_display = ("organization", "profile", "is_active", "activated_at")
    list_filter = ("is_active", "profile")
    search_fields = ("organization__name", "profile__name")


@admin.register(OrganizationCapability)
class OrganizationCapabilityAdmin(admin.ModelAdmin):
    list_display = ("organization", "capability", "status", "expires_on")
    list_filter = ("status", "capability__category")
    search_fields = ("organization__name", "capability__name")
