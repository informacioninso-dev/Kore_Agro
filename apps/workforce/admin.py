from django.contrib import admin

from .models import Worker, WorkLog, WorkTask


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("code", "full_name", "farm", "position", "hourly_rate", "is_active")
    list_filter = ("farm", "position", "is_active")
    search_fields = ("code", "full_name", "phone", "user__username")


@admin.register(WorkTask)
class WorkTaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "farm",
        "assigned_to",
        "scheduled_for",
        "priority",
        "status",
    )
    list_filter = ("farm", "category", "priority", "status", "scheduled_for")
    search_fields = ("title", "assigned_to__full_name")
    date_hierarchy = "scheduled_for"


@admin.register(WorkLog)
class WorkLogAdmin(admin.ModelAdmin):
    list_display = ("task", "worker", "work_date", "hours", "hourly_rate", "labor_cost")
    list_filter = ("work_date", "worker__farm")
    search_fields = ("task__title", "worker__full_name")
    date_hierarchy = "work_date"
