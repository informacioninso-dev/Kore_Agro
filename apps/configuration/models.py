from django.db import models
from django.utils import timezone

from apps.tenants.models import Client


class ProfileDefinition(models.Model):
    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "perfil de empresa"
        verbose_name_plural = "perfiles de empresa"

    def __str__(self) -> str:
        return self.name


class CapabilityDefinition(models.Model):
    class Category(models.TextChoices):
        FOUNDATION = "foundation", "Plataforma"
        OPERATIONS = "operations", "Operaciones"
        PRODUCTION = "production", "Produccion"
        INVENTORY = "inventory", "Inventario"
        FINANCE = "finance", "Finanzas"
        COMPLIANCE = "compliance", "Cumplimiento"
        ANALYTICS = "analytics", "Analitica"

    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.CharField(max_length=255, blank=True)
    compatible_profiles = models.ManyToManyField(
        ProfileDefinition,
        blank=True,
        related_name="capabilities",
    )
    dependencies = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=False,
        related_name="required_by",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "sort_order", "name"]
        verbose_name = "capacidad"
        verbose_name_plural = "capacidades"

    def __str__(self) -> str:
        return self.name


class OrganizationProfile(models.Model):
    organization = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="profile_assignments",
    )
    profile = models.ForeignKey(
        ProfileDefinition,
        on_delete=models.PROTECT,
        related_name="organization_assignments",
    )
    is_active = models.BooleanField(default=True)
    activated_at = models.DateTimeField(default=timezone.now)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["organization__name", "profile__sort_order", "profile__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "profile"],
                name="unique_profile_per_organization",
            )
        ]

    def __str__(self) -> str:
        return f"{self.organization.name} - {self.profile.name}"


class OrganizationCapability(models.Model):
    class Status(models.TextChoices):
        TRIAL = "trial", "Prueba"
        ENABLED = "enabled", "Habilitada"
        SUSPENDED = "suspended", "Suspendida"

    organization = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="capability_assignments",
    )
    capability = models.ForeignKey(
        CapabilityDefinition,
        on_delete=models.PROTECT,
        related_name="organization_assignments",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ENABLED)
    enabled_at = models.DateTimeField(default=timezone.now)
    expires_on = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["organization__name", "capability__category", "capability__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "capability"],
                name="unique_capability_per_organization",
            )
        ]

    def __str__(self) -> str:
        return f"{self.organization.name} - {self.capability.name}"

    @property
    def is_available(self) -> bool:
        if self.status not in {self.Status.TRIAL, self.Status.ENABLED}:
            return False
        return not self.expires_on or self.expires_on >= timezone.localdate()
