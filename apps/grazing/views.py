from decimal import Decimal

from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.herd.models import Farm

from .forms import FinishGrazingForm, PaddockForm, StartGrazingForm
from .models import GrazingPeriod, Paddock
from .services import finish_grazing_period, get_paddock_summaries, start_grazing_period


def _selected_farm(request: HttpRequest) -> Farm | None:
    farm_id = request.POST.get("farm") or request.GET.get("farm")
    if farm_id:
        return Farm.objects.filter(pk=farm_id, is_active=True).first()
    return Farm.objects.filter(is_active=True).order_by("name").first()


def _error_text(exc: ValidationError) -> str:
    return " ".join(exc.messages)


def _grazing_context(
    request: HttpRequest,
    *,
    farm: Farm | None = None,
    overrides: dict | None = None,
) -> dict:
    selected_farm = farm or _selected_farm(request)
    summaries = get_paddock_summaries(farm=selected_farm) if selected_farm else []
    active_rows = [row for row in summaries if row.active_period]
    recent_periods = (
        GrazingPeriod.objects.filter(farm=selected_farm, ended_on__isnull=False)
        .select_related("paddock", "group")
        .order_by("-ended_on", "-started_on")[:20]
        if selected_farm
        else []
    )
    context = {
        "farms": Farm.objects.filter(is_active=True).order_by("name"),
        "selected_farm": selected_farm,
        "paddock_rows": summaries,
        "active_rows": active_rows,
        "recent_periods": recent_periods,
        "paddock_count": len(summaries),
        "occupied_count": len(active_rows),
        "available_count": sum(1 for row in summaries if row.status == "available"),
        "occupied_hectares": sum(
            (row.paddock.area_hectares for row in active_rows),
            Decimal("0"),
        ),
        "paddock_form": PaddockForm(
            farm=selected_farm,
            initial={"farm": selected_farm},
        ),
        "start_form": StartGrazingForm(
            farm=selected_farm,
            initial={"farm": selected_farm},
        ),
        "finish_form": FinishGrazingForm(),
        "paddock_edit_id": None,
        "grazing_message": "",
        "grazing_error": "",
    }
    if overrides:
        context.update(overrides)
    return context


def dashboard(request: HttpRequest) -> HttpResponse:
    return render(request, "grazing/dashboard.html", _grazing_context(request))


@require_POST
def paddock_create(request: HttpRequest) -> HttpResponse:
    farm = _selected_farm(request)
    form = PaddockForm(request.POST, farm=farm)
    if not form.is_valid():
        return render(
            request,
            "grazing/dashboard.html",
            _grazing_context(
                request,
                farm=farm,
                overrides={
                    "paddock_form": form,
                    "grazing_error": "Revisa los datos del potrero.",
                },
            ),
            status=422,
        )
    paddock = form.save()
    return render(
        request,
        "grazing/dashboard.html",
        _grazing_context(
            request,
            farm=paddock.farm,
            overrides={"grazing_message": f"Potrero {paddock.name} creado."},
        ),
    )


def paddock_edit(request: HttpRequest, pk) -> HttpResponse:
    paddock = get_object_or_404(Paddock, pk=pk, is_active=True)
    return render(
        request,
        "grazing/dashboard.html",
        _grazing_context(
            request,
            farm=paddock.farm,
            overrides={
                "paddock_form": PaddockForm(instance=paddock, farm=paddock.farm),
                "paddock_edit_id": paddock.id,
            },
        ),
    )


@require_POST
def paddock_update(request: HttpRequest, pk) -> HttpResponse:
    paddock = get_object_or_404(Paddock, pk=pk, is_active=True)
    form = PaddockForm(request.POST, instance=paddock, farm=paddock.farm)
    if not form.is_valid():
        return render(
            request,
            "grazing/dashboard.html",
            _grazing_context(
                request,
                farm=paddock.farm,
                overrides={
                    "paddock_form": form,
                    "paddock_edit_id": paddock.id,
                    "grazing_error": "Revisa los datos del potrero.",
                },
            ),
            status=422,
        )
    paddock = form.save()
    return render(
        request,
        "grazing/dashboard.html",
        _grazing_context(
            request,
            farm=paddock.farm,
            overrides={"grazing_message": f"Potrero {paddock.name} actualizado."},
        ),
    )


@require_POST
def paddock_deactivate(request: HttpRequest, pk) -> HttpResponse:
    paddock = get_object_or_404(Paddock, pk=pk, is_active=True)
    if paddock.grazing_periods.filter(ended_on__isnull=True).exists():
        return render(
            request,
            "grazing/dashboard.html",
            _grazing_context(
                request,
                farm=paddock.farm,
                overrides={"grazing_error": "Cierra la ocupacion antes de desactivar el potrero."},
            ),
            status=422,
        )
    paddock.soft_delete()
    return render(
        request,
        "grazing/dashboard.html",
        _grazing_context(
            request,
            farm=paddock.farm,
            overrides={"grazing_message": f"Potrero {paddock.name} desactivado."},
        ),
    )


@require_POST
def rotation_start(request: HttpRequest) -> HttpResponse:
    farm = _selected_farm(request)
    form = StartGrazingForm(request.POST, farm=farm)
    if not form.is_valid():
        return render(
            request,
            "grazing/dashboard.html",
            _grazing_context(
                request,
                farm=farm,
                overrides={
                    "start_form": form,
                    "grazing_error": "Revisa los datos de entrada al potrero.",
                },
            ),
            status=422,
        )
    data = form.cleaned_data
    try:
        period = start_grazing_period(
            farm=data["farm"],
            paddock=data["paddock"],
            group=data["group"],
            started_on=data["started_on"],
            planned_end_on=data["planned_end_on"],
            head_count=data["head_count"],
            entry_biomass_kg_ha=data["entry_biomass_kg_ha"],
            notes=data["notes"],
        )
    except ValidationError as exc:
        return render(
            request,
            "grazing/dashboard.html",
            _grazing_context(
                request,
                farm=farm,
                overrides={"start_form": form, "grazing_error": _error_text(exc)},
            ),
            status=422,
        )
    return render(
        request,
        "grazing/dashboard.html",
        _grazing_context(
            request,
            farm=period.farm,
            overrides={
                "grazing_message": (
                    f"{period.group.name} ingreso a {period.paddock.name} "
                    f"con {period.head_count} animales."
                )
            },
        ),
    )


@require_POST
def rotation_finish(request: HttpRequest, pk) -> HttpResponse:
    period = get_object_or_404(
        GrazingPeriod.objects.select_related("farm", "paddock", "group"),
        pk=pk,
        ended_on__isnull=True,
    )
    form = FinishGrazingForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "grazing/dashboard.html",
            _grazing_context(
                request,
                farm=period.farm,
                overrides={
                    "finish_form": form,
                    "grazing_error": "Revisa la fecha y biomasa de salida.",
                },
            ),
            status=422,
        )
    data = form.cleaned_data
    try:
        period = finish_grazing_period(
            period,
            ended_on=data["ended_on"],
            exit_biomass_kg_ha=data["exit_biomass_kg_ha"],
            notes=data["notes"],
        )
    except ValidationError as exc:
        return render(
            request,
            "grazing/dashboard.html",
            _grazing_context(
                request,
                farm=period.farm,
                overrides={"finish_form": form, "grazing_error": _error_text(exc)},
            ),
            status=422,
        )
    return render(
        request,
        "grazing/dashboard.html",
        _grazing_context(
            request,
            farm=period.farm,
            overrides={
                "grazing_message": (
                    f"Salida registrada: {period.group.name} dejo {period.paddock.name}."
                )
            },
        ),
    )
