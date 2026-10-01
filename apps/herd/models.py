from decimal import Decimal

from django.db import models

from apps.common.models import SoftDeleteModel, TenantModel


class Farm(TenantModel, SoftDeleteModel):
    name = models.CharField(max_length=160)
    code = models.CharField(max_length=40, unique=True)
    province = models.CharField(max_length=80, blank=True)
    canton = models.CharField(max_length=80, blank=True)
    parish = models.CharField(max_length=80, blank=True)
    weather_location = models.CharField(
        max_length=160,
        blank=True,
        help_text="Parroquia o ciudad usada para consultar el pronostico.",
    )
    default_milk_price = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=Decimal("0.45"),
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class HerdGroup(TenantModel, SoftDeleteModel):
    class GroupType(models.TextChoices):
        LOT = "lot", "Lote"
        PADDOCK = "paddock", "Potrero"
        MANAGEMENT = "management", "Manejo"

    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="groups")
    name = models.CharField(max_length=120)
    group_type = models.CharField(max_length=20, choices=GroupType.choices, default=GroupType.LOT)

    class Meta:
        ordering = ["farm__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["farm", "name"], name="unique_group_name_per_farm"),
        ]

    def __str__(self) -> str:
        return f"{self.farm.code} - {self.name}"


class Animal(TenantModel, SoftDeleteModel):
    class Sex(models.TextChoices):
        FEMALE = "female", "Hembra"
        MALE = "male", "Macho"

    class Status(models.TextChoices):
        CALF = "calf", "Ternera"
        HEIFER = "heifer", "Vientre"
        LACTATING = "lactating", "En lactancia"
        DRY = "dry", "Seca"
        PREGNANT = "pregnant", "Prenada"
        SOLD = "sold", "Vendida"
        DEAD = "dead", "Muerta"
        CULLED = "culled", "Descartada"

    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="animals")
    current_group = models.ForeignKey(
        HerdGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="animals",
    )
    tag = models.CharField(max_length=40)
    name = models.CharField(max_length=120, blank=True)
    sex = models.CharField(max_length=10, choices=Sex.choices, default=Sex.FEMALE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.HEIFER)
    birth_date = models.DateField(null=True, blank=True)
    entry_date = models.DateField(null=True, blank=True)
    dam = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="offspring",
    )
    bos_taurus_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    bos_indicus_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    lactation_number = models.PositiveSmallIntegerField(default=0)
    last_calving_date = models.DateField(null=True, blank=True)
    last_service_date = models.DateField(null=True, blank=True)
    confirmed_pregnant_at = models.DateField(null=True, blank=True)
    expected_calving_date = models.DateField(null=True, blank=True)
    dry_off_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["tag"]
        constraints = [
            models.UniqueConstraint(fields=["farm", "tag"], name="unique_animal_tag_per_farm"),
        ]

    def __str__(self) -> str:
        return self.tag

    @property
    def days_in_milk(self) -> int | None:
        if not self.last_calving_date:
            return None
        from django.utils import timezone

        return (timezone.localdate() - self.last_calving_date).days
