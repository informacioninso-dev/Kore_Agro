from django.contrib import admin

from .models import Animal, Farm, HerdGroup


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "province", "default_milk_price", "is_active")
    search_fields = ("name", "code", "province")
    list_filter = ("province", "is_active")


@admin.register(HerdGroup)
class HerdGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "farm", "group_type", "is_active")
    search_fields = ("name", "farm__name")
    list_filter = ("group_type", "is_active")


@admin.register(Animal)
class AnimalAdmin(admin.ModelAdmin):
    list_display = ("tag", "name", "farm", "current_group", "status", "days_in_milk")
    search_fields = ("tag", "name")
    list_filter = ("status", "sex", "farm")

