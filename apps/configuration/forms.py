from django import forms
from django.core.exceptions import ValidationError

from apps.tenants.models import Client, Domain

from .models import (
    CapabilityDefinition,
    OrganizationCapability,
    OrganizationProfile,
    ProfileDefinition,
)


class PlatformFormMixin:
    field_class = "platform-input"
    checkbox_class = "platform-checkbox"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", self.checkbox_class)
            elif isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs.setdefault("class", "platform-checklist")
            else:
                field.widget.attrs.setdefault("class", self.field_class)


class PlatformModelForm(PlatformFormMixin, forms.ModelForm):
    pass


class OrganizationForm(PlatformModelForm):
    domain = forms.CharField(label="Dominio principal", max_length=253)
    profiles = forms.ModelMultipleChoiceField(
        label="Perfiles operativos",
        queryset=ProfileDefinition.objects.filter(is_active=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    capabilities = forms.ModelMultipleChoiceField(
        label="Capacidades habilitadas",
        queryset=CapabilityDefinition.objects.filter(is_active=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Las dependencias tecnicas se habilitan automaticamente.",
    )
    owner_username = forms.CharField(label="Usuario propietario", max_length=150)
    owner_email = forms.EmailField(label="Correo del propietario", required=False)
    owner_password = forms.CharField(
        label="Contraseña temporal",
        min_length=10,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = Client
        fields = [
            "name",
            "legal_name",
            "ruc",
            "province",
            "city",
            "schema_name",
            "paid_until",
            "on_trial",
        ]
        widgets = {
            "paid_until": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "name": "Nombre comercial",
            "legal_name": "Razon social",
            "ruc": "RUC",
            "province": "Provincia",
            "city": "Ciudad",
            "schema_name": "Esquema tecnico",
            "paid_until": "Servicio pagado hasta",
            "on_trial": "Organizacion en periodo de prueba",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["schema_name"].disabled = True
            primary_domain = self.instance.domains.filter(is_primary=True).first()
            self.fields["domain"].initial = primary_domain.domain if primary_domain else ""
            self.fields["profiles"].initial = self.instance.profile_assignments.filter(
                is_active=True
            ).values_list("profile_id", flat=True)
            self.fields["capabilities"].initial = self.instance.capability_assignments.filter(
                status__in=(
                    OrganizationCapability.Status.TRIAL,
                    OrganizationCapability.Status.ENABLED,
                )
            ).values_list("capability_id", flat=True)
            self.fields.pop("owner_username")
            self.fields.pop("owner_email")
            self.fields.pop("owner_password")

    def clean_schema_name(self):
        schema_name = self.cleaned_data["schema_name"].strip().lower()
        if schema_name == "public":
            raise ValidationError("El esquema public esta reservado para la plataforma.")
        return schema_name

    def clean_domain(self):
        domain = self.cleaned_data["domain"].strip().lower().rstrip(".")
        if "://" in domain or "/" in domain or ":" in domain:
            raise ValidationError("Escribe solo el dominio, sin protocolo, ruta ni puerto.")
        existing = Domain.objects.filter(domain=domain)
        if self.instance and self.instance.pk:
            existing = existing.exclude(tenant=self.instance)
        if existing.exists():
            raise ValidationError("Este dominio ya esta asignado a otra organizacion.")
        return domain

    def clean_capabilities(self):
        selected = list(self.cleaned_data["capabilities"].prefetch_related("dependencies"))
        capability_ids = {capability.id for capability in selected}
        pending = list(selected)
        while pending:
            capability = pending.pop()
            for dependency in capability.dependencies.filter(is_active=True):
                if dependency.id not in capability_ids:
                    capability_ids.add(dependency.id)
                    pending.append(dependency)

        selected_profile_ids = set(
            self.cleaned_data.get("profiles", ProfileDefinition.objects.none()).values_list(
                "id", flat=True
            )
        )
        incompatible = []
        capabilities = CapabilityDefinition.objects.filter(
            id__in=capability_ids
        ).prefetch_related("compatible_profiles")
        for capability in capabilities:
            compatible_ids = {profile.id for profile in capability.compatible_profiles.all()}
            if compatible_ids and not compatible_ids.intersection(selected_profile_ids):
                incompatible.append(capability.name)
        if incompatible:
            raise ValidationError(
                "Selecciona un perfil compatible con: " + ", ".join(sorted(incompatible))
            )
        return CapabilityDefinition.objects.filter(id__in=capability_ids)

    def save(self, commit=True):
        organization = super().save(commit=commit)
        if not commit:
            return organization

        primary_domain = organization.domains.filter(is_primary=True).first()
        if primary_domain:
            primary_domain.domain = self.cleaned_data["domain"]
            primary_domain.save(update_fields=["domain"])
        else:
            primary_domain = Domain.objects.create(
                tenant=organization,
                domain=self.cleaned_data["domain"],
                is_primary=True,
            )
        organization.domains.exclude(pk=primary_domain.pk).update(is_primary=False)

        selected_profiles = set(self.cleaned_data["profiles"].values_list("id", flat=True))
        organization.profile_assignments.exclude(profile_id__in=selected_profiles).update(
            is_active=False
        )
        for profile in self.cleaned_data["profiles"]:
            OrganizationProfile.objects.update_or_create(
                organization=organization,
                profile=profile,
                defaults={"is_active": True},
            )

        selected_capabilities = set(
            self.cleaned_data["capabilities"].values_list("id", flat=True)
        )
        organization.capability_assignments.exclude(
            capability_id__in=selected_capabilities
        ).update(status=OrganizationCapability.Status.SUSPENDED)
        capability_status = (
            OrganizationCapability.Status.TRIAL
            if organization.on_trial
            else OrganizationCapability.Status.ENABLED
        )
        for capability in self.cleaned_data["capabilities"]:
            OrganizationCapability.objects.update_or_create(
                organization=organization,
                capability=capability,
                defaults={"status": capability_status},
            )
        return organization


class ProfileDefinitionForm(PlatformModelForm):
    class Meta:
        model = ProfileDefinition
        fields = ["name", "code", "description", "sort_order", "is_active"]
        labels = {
            "name": "Nombre",
            "code": "Clave estable",
            "description": "Descripcion",
            "sort_order": "Orden",
            "is_active": "Perfil disponible",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["code"].disabled = True


class CapabilityDefinitionForm(PlatformModelForm):
    class Meta:
        model = CapabilityDefinition
        fields = [
            "name",
            "code",
            "category",
            "description",
            "compatible_profiles",
            "dependencies",
            "sort_order",
            "is_active",
        ]
        widgets = {
            "compatible_profiles": forms.CheckboxSelectMultiple,
            "dependencies": forms.CheckboxSelectMultiple,
        }
        labels = {
            "name": "Nombre",
            "code": "Clave estable",
            "category": "Categoria",
            "description": "Descripcion",
            "compatible_profiles": "Perfiles compatibles",
            "dependencies": "Capacidades requeridas",
            "sort_order": "Orden",
            "is_active": "Capacidad disponible",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["code"].disabled = True
            self.fields["dependencies"].queryset = CapabilityDefinition.objects.exclude(
                pk=self.instance.pk
            )
