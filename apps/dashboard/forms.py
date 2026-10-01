from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password

from apps.finance.models import CostAllocation
from apps.growth.models import WeightRecord
from apps.herd.models import Animal, Farm, HerdGroup
from apps.identity.access import ROLE_FIELD_WORKER, ROLE_LABELS
from apps.identity.models import FieldAssignment
from apps.inventory.models import Input, StockLot
from apps.tenants.models import Client

DIRECT_EXPENSE_CHOICES = [
    (value, label)
    for value, label in CostAllocation.CostType.choices
    if value in CostAllocation.DIRECT_EXPENSE_TYPES
]


class DarkModeStyleMixin:
    field_class = (
        "w-full rounded border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm "
        "text-white outline-none focus:border-emerald-500"
    )
    checkbox_class = "h-4 w-4 rounded border-neutral-700 bg-neutral-950 text-emerald-500"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field, forms.ModelChoiceField):
                field.empty_label = "- Seleccionar -"
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", self.checkbox_class)
            else:
                field.widget.attrs.setdefault("class", self.field_class)


class DarkModeForm(DarkModeStyleMixin, forms.Form):
    pass


class DarkModeModelForm(DarkModeStyleMixin, forms.ModelForm):
    pass


def _active_farms():
    return Farm.objects.filter(is_active=True).order_by("name")


def _active_groups():
    return HerdGroup.objects.filter(is_active=True).select_related("farm").order_by("name")


def _active_animals():
    return Animal.objects.filter(is_active=True).order_by("tag")


def _active_inputs():
    return Input.objects.filter(is_active=True).order_by("name")


class FarmForm(DarkModeModelForm):
    class Meta:
        model = Farm
        fields = [
            "name",
            "code",
            "province",
            "canton",
            "parish",
            "weather_location",
            "default_milk_price",
            "is_active",
        ]
        widgets = {
            "weather_location": forms.TextInput(attrs={"placeholder": "Ej. Tumbaco"}),
            "default_milk_price": forms.NumberInput(attrs={"step": "0.0001", "min": "0"}),
        }
        labels = {
            "name": "Nombre",
            "code": "Codigo",
            "province": "Provincia",
            "canton": "Canton",
            "parish": "Parroquia",
            "weather_location": "Ubicacion para clima",
            "default_milk_price": "Precio leche",
            "is_active": "Activa",
        }


class OrganizationSettingsForm(DarkModeModelForm):
    class Meta:
        model = Client
        fields = ["name", "legal_name", "ruc", "province", "city"]
        labels = {
            "name": "Nombre comercial",
            "legal_name": "Razon social",
            "ruc": "RUC",
            "province": "Provincia",
            "city": "Ciudad",
        }


class FarmSettingsForm(DarkModeModelForm):
    class Meta:
        model = Farm
        fields = [
            "name",
            "code",
            "province",
            "canton",
            "parish",
            "weather_location",
            "default_milk_price",
        ]
        widgets = {
            "weather_location": forms.TextInput(attrs={"placeholder": "Ej. Tumbaco"}),
            "default_milk_price": forms.NumberInput(attrs={"step": "0.0001", "min": "0"}),
        }
        labels = {
            "name": "Nombre",
            "code": "Codigo",
            "province": "Provincia",
            "canton": "Canton",
            "parish": "Parroquia",
            "weather_location": "Ubicacion para clima",
            "default_milk_price": "Precio de leche",
        }


class TenantUserForm(DarkModeForm):
    username = forms.CharField(label="Usuario", max_length=150)
    first_name = forms.CharField(label="Nombres", max_length=150, required=False)
    last_name = forms.CharField(label="Apellidos", max_length=150, required=False)
    email = forms.EmailField(label="Correo", required=False)
    role = forms.ChoiceField(label="Rol", choices=tuple(ROLE_LABELS.items()))
    farm = forms.ModelChoiceField(
        label="Hacienda asignada",
        queryset=Farm.objects.none(),
        required=False,
    )
    password = forms.CharField(
        label="Contrasena",
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    is_active = forms.BooleanField(label="Usuario activo", required=False, initial=True)

    def __init__(self, *args, user_instance=None, **kwargs):
        self.user_instance = user_instance
        super().__init__(*args, **kwargs)
        self.fields["farm"].queryset = _active_farms()
        if user_instance and not self.is_bound:
            assignment = getattr(user_instance, "field_assignment", None)
            role = (
                user_instance.groups.filter(name__in=ROLE_LABELS)
                .values_list("name", flat=True)
                .first()
            )
            self.initial.update(
                {
                    "username": user_instance.username,
                    "first_name": user_instance.first_name,
                    "last_name": user_instance.last_name,
                    "email": user_instance.email,
                    "role": role,
                    "farm": assignment.farm_id if assignment and assignment.is_active else None,
                    "is_active": user_instance.is_active,
                }
            )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        users = get_user_model().objects.filter(username__iexact=username)
        if self.user_instance:
            users = users.exclude(pk=self.user_instance.pk)
        if users.exists():
            raise forms.ValidationError("Ya existe un usuario con ese nombre.")
        return username

    def clean_password(self):
        password = self.cleaned_data.get("password", "")
        if not self.user_instance and not password:
            raise forms.ValidationError("Define una contrasena para el usuario.")
        if password:
            candidate = self.user_instance or get_user_model()(
                username=self.cleaned_data.get("username", ""),
                email=self.cleaned_data.get("email", ""),
            )
            validate_password(password, candidate)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("role") == ROLE_FIELD_WORKER and not cleaned.get("farm"):
            self.add_error("farm", "Selecciona la hacienda del mayordomo.")
        return cleaned

    def save(self):
        data = self.cleaned_data
        user = self.user_instance or get_user_model()()
        user.username = data["username"]
        user.first_name = data["first_name"]
        user.last_name = data["last_name"]
        user.email = data["email"]
        user.is_active = data["is_active"]
        if data["password"]:
            user.set_password(data["password"])
        user.save()

        role_groups = Group.objects.filter(name__in=ROLE_LABELS)
        user.groups.remove(*role_groups)
        user.groups.add(Group.objects.get(name=data["role"]))

        if data["role"] == ROLE_FIELD_WORKER:
            FieldAssignment.objects.update_or_create(
                user=user,
                defaults={"farm": data["farm"], "is_active": True},
            )
        else:
            FieldAssignment.objects.filter(user=user).delete()
        return user


class HerdGroupForm(DarkModeModelForm):
    class Meta:
        model = HerdGroup
        fields = ["farm", "name", "group_type", "is_active"]
        labels = {
            "farm": "Hacienda",
            "name": "Nombre",
            "group_type": "Tipo",
            "is_active": "Activo",
        }


class AnimalForm(DarkModeModelForm):
    class Meta:
        model = Animal
        fields = [
            "farm",
            "current_group",
            "tag",
            "name",
            "sex",
            "status",
            "birth_date",
            "entry_date",
            "dam",
            "bos_taurus_pct",
            "bos_indicus_pct",
            "last_calving_date",
            "last_service_date",
            "expected_calving_date",
            "dry_off_date",
            "notes",
            "is_active",
        ]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "entry_date": forms.DateInput(attrs={"type": "date"}),
            "last_calving_date": forms.DateInput(attrs={"type": "date"}),
            "last_service_date": forms.DateInput(attrs={"type": "date"}),
            "expected_calving_date": forms.DateInput(attrs={"type": "date"}),
            "dry_off_date": forms.DateInput(attrs={"type": "date"}),
            "bos_taurus_pct": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100"}),
            "bos_indicus_pct": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "farm": "Hacienda",
            "current_group": "Lote",
            "tag": "Arete",
            "name": "Nombre",
            "sex": "Sexo",
            "status": "Estado",
            "birth_date": "Nacimiento",
            "entry_date": "Ingreso",
            "dam": "Madre",
            "bos_taurus_pct": "% Taurus",
            "bos_indicus_pct": "% Indicus",
            "last_calving_date": "Ultimo parto",
            "last_service_date": "Ultimo servicio",
            "expected_calving_date": "Parto esperado",
            "dry_off_date": "Secado",
            "notes": "Notas",
            "is_active": "Activo",
        }


class WeightRecordForm(DarkModeModelForm):
    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["animal"].queryset = _active_animals().select_related("farm")
        if farm:
            self.fields["animal"].queryset = self.fields["animal"].queryset.filter(farm=farm)
            self.fields["farm"].initial = farm

    class Meta:
        model = WeightRecord
        fields = [
            "farm",
            "animal",
            "weighed_on",
            "weight_kg",
            "body_condition_score",
            "scale_identifier",
            "notes",
        ]
        widgets = {
            "farm": forms.HiddenInput(),
            "weighed_on": forms.DateInput(attrs={"type": "date"}),
            "weight_kg": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "body_condition_score": forms.NumberInput(
                attrs={"step": "0.1", "min": "1", "max": "5"}
            ),
        }
        labels = {
            "animal": "Animal",
            "weighed_on": "Fecha del pesaje",
            "weight_kg": "Peso (kg)",
            "body_condition_score": "Condicion corporal (1-5)",
            "scale_identifier": "Bascula o equipo",
            "notes": "Notas",
        }


class InputForm(DarkModeModelForm):
    class Meta:
        model = Input
        fields = [
            "name",
            "sku",
            "category",
            "unit",
            "default_unit_cost",
            "milk_withdrawal_hours",
            "is_active",
        ]
        widgets = {
            "default_unit_cost": forms.NumberInput(attrs={"step": "0.0001", "min": "0"}),
            "milk_withdrawal_hours": forms.NumberInput(attrs={"min": "0"}),
        }
        labels = {
            "name": "Nombre",
            "sku": "SKU",
            "category": "Categoria",
            "unit": "Unidad",
            "default_unit_cost": "Costo unitario",
            "milk_withdrawal_hours": "Retiro leche horas",
            "is_active": "Activo",
        }


class StockLotForm(DarkModeModelForm):
    class Meta:
        model = StockLot
        fields = [
            "farm",
            "input",
            "lot_code",
            "expires_on",
            "quantity_on_hand",
            "unit_cost",
            "is_active",
        ]
        widgets = {
            "expires_on": forms.DateInput(attrs={"type": "date"}),
            "quantity_on_hand": forms.NumberInput(attrs={"step": "0.001", "min": "0"}),
            "unit_cost": forms.NumberInput(attrs={"step": "0.0001", "min": "0"}),
        }
        labels = {
            "farm": "Hacienda",
            "input": "Insumo",
            "lot_code": "Lote proveedor",
            "expires_on": "Vence",
            "quantity_on_hand": "Existencia",
            "unit_cost": "Costo unitario",
            "is_active": "Activo",
        }


class OperatingExpenseForm(DarkModeForm):
    """Direct operating cost that never passes through the warehouse."""

    farm = forms.ModelChoiceField(queryset=_active_farms(), label="Hacienda")
    group = forms.ModelChoiceField(queryset=_active_groups(), label="Lote", required=False)
    animal = forms.ModelChoiceField(queryset=_active_animals(), label="Animal", required=False)
    cost_type = forms.ChoiceField(choices=DIRECT_EXPENSE_CHOICES, label="Tipo")
    cost_date = forms.DateField(
        label="Fecha",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    amount = forms.DecimalField(
        label="Monto",
        max_digits=14,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
    )
    notes = forms.CharField(label="Detalle", max_length=255, required=False)


class AnimalSaleForm(DarkModeForm):
    farm = forms.ModelChoiceField(queryset=_active_farms(), label="Hacienda")
    animal = forms.ModelChoiceField(queryset=_active_animals(), label="Animal")
    sale_date = forms.DateField(
        label="Fecha",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    amount = forms.DecimalField(
        label="Valor venta",
        max_digits=14,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
    )
    notes = forms.CharField(label="Detalle", max_length=255, required=False)


class InputReceiptForm(DarkModeForm):
    """Purchase/reception: money enters inventory, not the P&L."""

    farm = forms.ModelChoiceField(queryset=_active_farms(), label="Hacienda")
    input = forms.ModelChoiceField(queryset=_active_inputs(), label="Insumo")
    quantity = forms.DecimalField(
        label="Cantidad",
        max_digits=14,
        decimal_places=3,
        min_value=Decimal("0.001"),
        widget=forms.NumberInput(attrs={"step": "0.001", "min": "0"}),
    )
    unit_cost = forms.DecimalField(
        label="Costo unitario",
        max_digits=12,
        decimal_places=4,
        required=False,
        min_value=Decimal("0"),
        widget=forms.NumberInput(attrs={"step": "0.0001", "min": "0"}),
    )
    lot_code = forms.CharField(label="Lote proveedor", max_length=80, required=False)
    expires_on = forms.DateField(
        label="Vence",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    notes = forms.CharField(label="Detalle", max_length=255, required=False)


class StockAdjustmentForm(DarkModeForm):
    """Physical count correction; a shortfall books a shrinkage cost."""

    farm = forms.ModelChoiceField(queryset=_active_farms(), label="Hacienda")
    input = forms.ModelChoiceField(queryset=_active_inputs(), label="Insumo")
    quantity_delta = forms.DecimalField(
        label="Diferencia (+/-)",
        max_digits=14,
        decimal_places=3,
        widget=forms.NumberInput(attrs={"step": "0.001"}),
    )
    reason = forms.CharField(label="Motivo", max_length=160)

    def clean_quantity_delta(self):
        delta = self.cleaned_data["quantity_delta"]
        if delta == 0:
            raise forms.ValidationError("La diferencia no puede ser cero.")
        return delta
