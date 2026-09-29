from django import forms
from django.utils import timezone

from apps.herd.models import Farm, HerdGroup

from .models import Paddock


class FormStyleMixin:
    field_class = (
        "w-full rounded border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm "
        "text-white outline-none focus:border-emerald-500"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field, forms.ModelChoiceField):
                field.empty_label = "- Seleccionar -"
            if not isinstance(field.widget, forms.HiddenInput):
                field.widget.attrs.setdefault("class", self.field_class)


class PaddockForm(FormStyleMixin, forms.ModelForm):
    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["farm"].queryset = Farm.objects.filter(is_active=True)
        if farm:
            self.fields["farm"].initial = farm

    class Meta:
        model = Paddock
        fields = [
            "farm",
            "name",
            "code",
            "area_hectares",
            "forage_type",
            "rest_target_days",
            "capacity_animals",
            "notes",
        ]
        widgets = {
            "farm": forms.HiddenInput(),
            "area_hectares": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "rest_target_days": forms.NumberInput(attrs={"min": "1"}),
            "capacity_animals": forms.NumberInput(attrs={"min": "1"}),
        }
        labels = {
            "name": "Nombre",
            "code": "Codigo",
            "area_hectares": "Area (ha)",
            "forage_type": "Tipo de forraje",
            "rest_target_days": "Descanso objetivo (dias)",
            "capacity_animals": "Capacidad de animales",
            "notes": "Notas",
        }


class StartGrazingForm(FormStyleMixin, forms.Form):
    farm = forms.ModelChoiceField(
        queryset=Farm.objects.none(),
        widget=forms.HiddenInput(),
    )
    paddock = forms.ModelChoiceField(queryset=Paddock.objects.none(), label="Potrero")
    group = forms.ModelChoiceField(queryset=HerdGroup.objects.none(), label="Lote de animales")
    started_on = forms.DateField(
        label="Fecha de entrada",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    planned_end_on = forms.DateField(
        label="Salida prevista",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    head_count = forms.IntegerField(label="Numero de animales", min_value=1, required=False)
    entry_biomass_kg_ha = forms.DecimalField(
        label="Biomasa de entrada (kg/ha)",
        max_digits=10,
        decimal_places=2,
        min_value=0.01,
        required=False,
    )
    notes = forms.CharField(label="Notas", max_length=255, required=False)

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["farm"].queryset = Farm.objects.filter(is_active=True)
        if farm:
            self.fields["farm"].initial = farm
            self.fields["paddock"].queryset = Paddock.objects.filter(
                farm=farm,
                is_active=True,
            )
            self.fields["group"].queryset = HerdGroup.objects.filter(
                farm=farm,
                is_active=True,
            )

    def clean(self):
        data = super().clean()
        farm = data.get("farm")
        paddock = data.get("paddock")
        group = data.get("group")
        if farm and paddock and paddock.farm_id != farm.id:
            self.add_error("paddock", "El potrero no pertenece a la hacienda.")
        if farm and group and group.farm_id != farm.id:
            self.add_error("group", "El lote no pertenece a la hacienda.")
        if data.get("started_on") and data["started_on"] > timezone.localdate():
            self.add_error("started_on", "La entrada no puede estar en el futuro.")
        if data.get("planned_end_on") and data.get("started_on"):
            if data["planned_end_on"] < data["started_on"]:
                self.add_error("planned_end_on", "La salida prevista debe ser posterior.")
        return data


class FinishGrazingForm(FormStyleMixin, forms.Form):
    ended_on = forms.DateField(
        label="Fecha de salida",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    exit_biomass_kg_ha = forms.DecimalField(
        label="Biomasa de salida (kg/ha)",
        max_digits=10,
        decimal_places=2,
        min_value=0.01,
        required=False,
    )
    notes = forms.CharField(label="Notas", max_length=255, required=False)

    def clean_ended_on(self):
        ended_on = self.cleaned_data["ended_on"]
        if ended_on > timezone.localdate():
            raise forms.ValidationError("La salida no puede estar en el futuro.")
        return ended_on
