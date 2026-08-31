from django import forms

from apps.dashboard.forms import DarkModeForm, DarkModeModelForm
from apps.herd.models import Animal, Farm

from .models import AnimalMovementGuide


class MilkInvoiceDraftForm(DarkModeForm):
    farm = forms.ModelChoiceField(queryset=Farm.objects.filter(is_active=True), label="Hacienda")
    buyer_ruc = forms.CharField(label="RUC comprador", max_length=13)
    buyer_name = forms.CharField(label="Comprador", max_length=200)
    period_start = forms.DateField(
        label="Desde", widget=forms.DateInput(attrs={"type": "date"})
    )
    period_end = forms.DateField(
        label="Hasta", widget=forms.DateInput(attrs={"type": "date"})
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("period_start") and cleaned.get("period_end"):
            if cleaned["period_end"] < cleaned["period_start"]:
                self.add_error("period_end", "Debe ser igual o posterior a la fecha inicial.")
        return cleaned


class AnimalMovementGuideForm(DarkModeModelForm):
    animals = forms.ModelMultipleChoiceField(
        queryset=Animal.objects.filter(is_active=True).order_by("tag"),
        label="Animales",
        required=True,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = AnimalMovementGuide
        fields = [
            "farm",
            "issue_date",
            "origin",
            "destination",
            "reason",
            "transporter_ruc",
            "transporter_name",
            "animals",
        ]
        widgets = {"issue_date": forms.DateInput(attrs={"type": "date"})}
        labels = {
            "farm": "Hacienda",
            "issue_date": "Fecha",
            "origin": "Origen",
            "destination": "Destino",
            "reason": "Motivo",
            "transporter_ruc": "RUC transportista",
            "transporter_name": "Transportista",
        }

    def clean(self):
        cleaned = super().clean()
        farm = cleaned.get("farm")
        animals = cleaned.get("animals")
        if farm and animals and animals.exclude(farm=farm).exists():
            self.add_error(
                "animals", "Todos los animales deben pertenecer a la hacienda seleccionada."
            )
        return cleaned
