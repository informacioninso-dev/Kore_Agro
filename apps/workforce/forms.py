from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.grazing.models import Paddock
from apps.herd.models import Animal, Farm, HerdGroup

from .models import Worker, WorkTask


class FormStyleMixin:
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
            elif not isinstance(field.widget, forms.HiddenInput):
                field.widget.attrs.setdefault("class", self.field_class)


class WorkerForm(FormStyleMixin, forms.ModelForm):
    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["farm"].queryset = Farm.objects.filter(is_active=True)
        linked_user_id = self.instance.user_id if self.instance.pk else None
        users = get_user_model().objects.filter(is_active=True).order_by("username")
        self.fields["user"].queryset = users.filter(
            Q(worker_profile__isnull=True) | Q(pk=linked_user_id)
        )
        if farm:
            self.fields["farm"].initial = farm

    class Meta:
        model = Worker
        fields = [
            "farm",
            "code",
            "full_name",
            "position",
            "phone",
            "hourly_rate",
            "hired_on",
            "user",
            "notes",
        ]
        widgets = {
            "farm": forms.HiddenInput(),
            "hourly_rate": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "hired_on": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "code": "Codigo",
            "full_name": "Nombre completo",
            "position": "Cargo",
            "phone": "Telefono",
            "hourly_rate": "Costo por hora",
            "hired_on": "Fecha de ingreso",
            "user": "Usuario de campo",
            "notes": "Notas",
        }


class WorkTaskForm(FormStyleMixin, forms.ModelForm):
    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["farm"].queryset = Farm.objects.filter(is_active=True)
        if farm:
            self.fields["farm"].initial = farm
            self.fields["assigned_to"].queryset = Worker.objects.filter(
                farm=farm,
                is_active=True,
            )
            self.fields["group"].queryset = HerdGroup.objects.filter(
                farm=farm,
                is_active=True,
            )
            self.fields["animal"].queryset = Animal.objects.filter(
                farm=farm,
                is_active=True,
            )
            self.fields["paddock"].queryset = Paddock.objects.filter(
                farm=farm,
                is_active=True,
            )

    class Meta:
        model = WorkTask
        fields = [
            "farm",
            "title",
            "category",
            "priority",
            "assigned_to",
            "scheduled_for",
            "due_time",
            "estimated_hours",
            "group",
            "animal",
            "paddock",
            "instructions",
        ]
        widgets = {
            "farm": forms.HiddenInput(),
            "scheduled_for": forms.DateInput(attrs={"type": "date"}),
            "due_time": forms.TimeInput(attrs={"type": "time"}),
            "estimated_hours": forms.NumberInput(attrs={"step": "0.25", "min": "0.01"}),
            "instructions": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "title": "Tarea",
            "category": "Tipo",
            "priority": "Prioridad",
            "assigned_to": "Responsable",
            "scheduled_for": "Fecha programada",
            "due_time": "Hora limite",
            "estimated_hours": "Horas estimadas",
            "group": "Lote",
            "animal": "Animal",
            "paddock": "Potrero",
            "instructions": "Indicaciones",
        }


class TaskActionForm(FormStyleMixin, forms.Form):
    class Action:
        START = "start"
        COMPLETE = "complete"

    task = forms.ModelChoiceField(queryset=WorkTask.objects.none(), label="Tarea")
    action = forms.ChoiceField(
        label="Accion",
        choices=((Action.START, "Iniciar"), (Action.COMPLETE, "Completar")),
    )
    worker = forms.ModelChoiceField(
        queryset=Worker.objects.none(),
        label="Trabajador",
        required=False,
    )
    hours = forms.DecimalField(
        label="Horas trabajadas",
        max_digits=7,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
        widget=forms.NumberInput(attrs={"step": "0.25", "min": "0.01"}),
    )
    notes = forms.CharField(label="Resultado o novedad", max_length=255, required=False)

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if farm:
            self.fields["task"].queryset = WorkTask.objects.filter(
                farm=farm,
                status__in=(WorkTask.Status.PENDING, WorkTask.Status.IN_PROGRESS),
            ).select_related("assigned_to")
            self.fields["worker"].queryset = Worker.objects.filter(farm=farm, is_active=True)

    def clean(self):
        data = super().clean()
        task = data.get("task")
        worker = data.get("worker")
        if task and worker and task.farm_id != worker.farm_id:
            self.add_error("worker", "El trabajador no pertenece a la hacienda.")
        if data.get("action") == self.Action.COMPLETE and not data.get("hours"):
            self.add_error("hours", "Indica las horas para completar la tarea.")
        return data
