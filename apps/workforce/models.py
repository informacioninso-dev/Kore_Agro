from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.common.models import SoftDeleteModel, TenantModel
from apps.grazing.models import Paddock
from apps.herd.models import Animal, Farm, HerdGroup


class Worker(TenantModel, SoftDeleteModel):
    class Position(models.TextChoices):
        FOREMAN = "foreman", "Mayordomo"
        LIVESTOCK = "livestock", "Ganaderia"
        MILKING = "milking", "Ordeno"
        AGRICULTURE = "agriculture", "Campo y cultivo"
        TECHNICIAN = "technician", "Tecnico"
        ADMINISTRATION = "administration", "Administracion"
        OTHER = "other", "Otro"

    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="workers")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="worker_profile",
    )
    code = models.CharField(max_length=40)
    full_name = models.CharField(max_length=160)
    position = models.CharField(max_length=30, choices=Position.choices, default=Position.OTHER)
    phone = models.CharField(max_length=40, blank=True)
    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    hired_on = models.DateField(default=timezone.localdate)
    ended_on = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["farm__name", "full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "code"],
                name="unique_worker_code_per_farm",
            ),
            models.CheckConstraint(
                condition=models.Q(hourly_rate__gte=0),
                name="nonnegative_worker_hourly_rate",
            ),
            models.CheckConstraint(
                condition=models.Q(ended_on__isnull=True)
                | models.Q(ended_on__gte=models.F("hired_on")),
                name="worker_end_after_hire",
            ),
        ]

    def clean(self) -> None:
        if self.ended_on and self.ended_on < self.hired_on:
            raise ValidationError({"ended_on": "La salida no puede ser anterior al ingreso."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.code} - {self.full_name}"


class WorkTask(TenantModel):
    class Category(models.TextChoices):
        LIVESTOCK = "livestock", "Hato"
        MILKING = "milking", "Ordeno"
        HEALTH = "health", "Sanidad"
        REPRODUCTION = "reproduction", "Reproduccion"
        GRAZING = "grazing", "Pastoreo"
        INVENTORY = "inventory", "Bodega"
        MAINTENANCE = "maintenance", "Mantenimiento"
        OTHER = "other", "Otro"

    class Priority(models.TextChoices):
        LOW = "low", "Baja"
        NORMAL = "normal", "Normal"
        HIGH = "high", "Alta"
        URGENT = "urgent", "Urgente"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        IN_PROGRESS = "in_progress", "En curso"
        COMPLETED = "completed", "Completada"
        CANCELLED = "cancelled", "Cancelada"

    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="work_tasks")
    title = models.CharField(max_length=160)
    category = models.CharField(max_length=30, choices=Category.choices)
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    assigned_to = models.ForeignKey(
        Worker,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tasks",
    )
    scheduled_for = models.DateField(default=timezone.localdate)
    due_time = models.TimeField(null=True, blank=True)
    estimated_hours = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    group = models.ForeignKey(
        HerdGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_tasks",
    )
    animal = models.ForeignKey(
        Animal,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_tasks",
    )
    paddock = models.ForeignKey(
        Paddock,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_tasks",
    )
    instructions = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["scheduled_for", "-priority", "created_at"]
        indexes = [
            models.Index(fields=["farm", "scheduled_for", "status"]),
            models.Index(fields=["assigned_to", "scheduled_for", "status"]),
        ]

    def clean(self) -> None:
        errors = {}
        relations = {
            "assigned_to": self.assigned_to,
            "group": self.group,
            "animal": self.animal,
            "paddock": self.paddock,
        }
        for field, related in relations.items():
            if related and self.farm_id and related.farm_id != self.farm_id:
                errors[field] = "El registro no pertenece a la hacienda seleccionada."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_overdue(self) -> bool:
        return (
            self.status in {self.Status.PENDING, self.Status.IN_PROGRESS}
            and self.scheduled_for < timezone.localdate()
        )

    def __str__(self) -> str:
        return self.title


class WorkLog(TenantModel):
    task = models.ForeignKey(WorkTask, on_delete=models.PROTECT, related_name="work_logs")
    worker = models.ForeignKey(Worker, on_delete=models.PROTECT, related_name="work_logs")
    work_date = models.DateField(default=timezone.localdate)
    hours = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0"))],
    )
    labor_cost = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0"))],
    )
    cost_allocation = models.OneToOneField(
        "finance.CostAllocation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_log",
    )
    source_event_id = models.UUIDField(null=True, blank=True, db_index=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-work_date", "-created_at"]
        indexes = [models.Index(fields=["worker", "work_date"])]
        constraints = [
            models.UniqueConstraint(
                fields=["source_event_id"],
                condition=models.Q(source_event_id__isnull=False),
                name="unique_work_log_source_event",
            ),
            models.CheckConstraint(
                condition=models.Q(hours__gt=0),
                name="positive_work_log_hours",
            ),
            models.CheckConstraint(
                condition=models.Q(labor_cost__gte=0),
                name="nonnegative_work_log_cost",
            ),
        ]

    def clean(self) -> None:
        if self.task_id and self.worker_id and self.task.farm_id != self.worker.farm_id:
            raise ValidationError({"worker": "El trabajador no pertenece a la hacienda."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.worker.full_name}: {self.hours} h - {self.task.title}"
