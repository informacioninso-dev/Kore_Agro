from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import SoftDeleteModel, TenantModel


class Counterparty(TenantModel, SoftDeleteModel):
    class IdentificationType(models.TextChoices):
        RUC = "ruc", "RUC"
        CEDULA = "cedula", "Cedula"
        PASSPORT = "passport", "Pasaporte"
        OTHER = "other", "Otro"

    legal_name = models.CharField(max_length=180)
    trade_name = models.CharField(max_length=180, blank=True)
    identification_type = models.CharField(
        max_length=20,
        choices=IdentificationType.choices,
        default=IdentificationType.RUC,
    )
    identification_number = models.CharField(max_length=30, blank=True)
    is_supplier = models.BooleanField(default=False)
    is_producer = models.BooleanField(default=False)
    is_customer = models.BooleanField(default=False)
    is_carrier = models.BooleanField(default=False)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=255, blank=True)
    province = models.CharField(max_length=80, blank=True)
    city = models.CharField(max_length=80, blank=True)
    payment_terms_days = models.PositiveSmallIntegerField(default=0)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["legal_name"]
        verbose_name = "contraparte"
        verbose_name_plural = "contrapartes"
        constraints = [
            models.UniqueConstraint(
                fields=["identification_number"],
                condition=~models.Q(identification_number=""),
                name="unique_counterparty_identification",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_supplier=True)
                    | models.Q(is_producer=True)
                    | models.Q(is_customer=True)
                    | models.Q(is_carrier=True)
                ),
                name="counterparty_has_role",
            ),
        ]

    @property
    def display_name(self) -> str:
        return self.trade_name or self.legal_name

    @property
    def role_labels(self) -> str:
        roles = []
        if self.is_supplier:
            roles.append("Proveedor")
        if self.is_producer:
            roles.append("Productor")
        if self.is_customer:
            roles.append("Cliente")
        if self.is_carrier:
            roles.append("Transportista")
        return ", ".join(roles)

    def clean(self) -> None:
        if not any((self.is_supplier, self.is_producer, self.is_customer, self.is_carrier)):
            raise ValidationError("Selecciona al menos un rol para la contraparte.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.display_name
