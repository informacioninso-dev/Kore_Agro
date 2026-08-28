from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.common.models import TenantModel
from apps.herd.models import Animal, Farm


class MilkInvoice(TenantModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        SIGNED = "signed", "Firmada"
        SUBMITTED = "submitted", "Enviada"
        AUTHORIZED = "authorized", "Autorizada"
        REJECTED = "rejected", "Rechazada"

    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="milk_invoices")
    issue_date = models.DateField(default=timezone.localdate)
    buyer_ruc = models.CharField(max_length=13)
    buyer_name = models.CharField(max_length=200)
    period_start = models.DateField()
    period_end = models.DateField()
    liters = models.DecimalField(max_digits=14, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=4)
    subtotal = models.DecimalField(max_digits=14, decimal_places=4)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0"))
    total = models.DecimalField(max_digits=14, decimal_places=4)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    access_key = models.CharField(max_length=49, blank=True, db_index=True)
    authorization_number = models.CharField(max_length=80, blank=True)
    authorization_date = models.DateTimeField(null=True, blank=True)
    sri_response = models.JSONField(default=dict, blank=True)
    source_event_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-issue_date", "-created_at"]
        indexes = [
            models.Index(fields=["issue_date"]),
            models.Index(fields=["status"]),
            models.Index(fields=["access_key"]),
        ]

    def __str__(self) -> str:
        return f"{self.buyer_name} {self.issue_date} {self.total}"


class AnimalMovementGuide(TenantModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        SIGNED = "signed", "Firmada"
        SUBMITTED = "submitted", "Enviada"
        AUTHORIZED = "authorized", "Autorizada"
        REJECTED = "rejected", "Rechazada"

    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="movement_guides")
    issue_date = models.DateField(default=timezone.localdate)
    origin = models.CharField(max_length=200)
    destination = models.CharField(max_length=200)
    reason = models.CharField(max_length=160)
    transporter_ruc = models.CharField(max_length=13, blank=True)
    transporter_name = models.CharField(max_length=200, blank=True)
    animals = models.ManyToManyField(Animal, related_name="movement_guides", blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    access_key = models.CharField(max_length=49, blank=True, db_index=True)
    authorization_number = models.CharField(max_length=80, blank=True)
    authorization_date = models.DateTimeField(null=True, blank=True)
    sri_response = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-issue_date", "-created_at"]
        indexes = [
            models.Index(fields=["issue_date"]),
            models.Index(fields=["status"]),
            models.Index(fields=["access_key"]),
        ]

    def __str__(self) -> str:
        return f"Guia {self.origin} -> {self.destination}"

