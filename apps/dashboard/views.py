from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.configuration.access import request_capability_codes
from apps.finance.models import CostAllocation, RevenueEntry
from apps.finance.services import (
    close_operating_period,
    get_animal_pnl,
    get_cost_breakdown,
    get_daily_pnl,
    get_event_trace,
    get_group_pnl,
    get_operating_pnl,
    get_recent_snapshots,
    get_unassigned_financial_lines,
    record_animal_sale,
    record_operating_expense,
)
from apps.growth.models import WeightRecord
from apps.growth.services import (
    get_animal_growth,
    get_growth_metrics,
    record_weight,
    summarize_groups,
)
from apps.health.models import Treatment
from apps.health.services import active_milk_withdrawals, open_treatments
from apps.herd.models import Animal, Farm, HerdGroup
from apps.inventory.models import Input, InventoryMovement, StockLot
from apps.inventory.services import adjust_stock, receive_input
from apps.milk.models import MilkYield
from apps.reproduction.models import ReproductionEvent
from apps.reproduction.services import daily_reproduction_attention

from .forms import (
    AnimalForm,
    AnimalSaleForm,
    FarmForm,
    HerdGroupForm,
    InputForm,
    InputReceiptForm,
    OperatingExpenseForm,
    StockAdjustmentForm,
    StockLotForm,
    WeightRecordForm,
)


class CrudSpec(NamedTuple):
    model: type
    form_class: type
    form_key: str
    edit_key: str
    success_message: str


FARM_SPEC = CrudSpec(Farm, FarmForm, "farm_form", "farm_edit_id", "Hacienda guardada.")
GROUP_SPEC = CrudSpec(HerdGroup, HerdGroupForm, "group_form", "group_edit_id", "Lote guardado.")
ANIMAL_SPEC = CrudSpec(Animal, AnimalForm, "animal_form", "animal_edit_id", "Animal guardado.")
INPUT_SPEC = CrudSpec(Input, InputForm, "input_form", "input_edit_id", "Insumo guardado.")
STOCK_SPEC = CrudSpec(
    StockLot,
    StockLotForm,
    "stock_lot_form",
    "stock_lot_edit_id",
    "Stock guardado.",
)


def _date_range(request):
    today = timezone.localdate()
    default_start = today - timedelta(days=30)
    start = parse_date(_request_value(request, "start"))
    end = parse_date(_request_value(request, "end"))
    return start or default_start, end or today


def _request_value(request: HttpRequest, key: str) -> str:
    return request.POST.get(key) or request.GET.get(key, "")


def _selected_farm(request):
    farm_id = _request_value(request, "farm")
    if farm_id:
        return Farm.objects.filter(id=farm_id, is_active=True).first()
    return Farm.objects.filter(is_active=True).order_by("name").first()


def _selected_group(request, farm: Farm | None) -> HerdGroup | None:
    group_id = _request_value(request, "group")
    if not group_id or not farm:
        return None
    return HerdGroup.objects.filter(id=group_id, farm=farm, is_active=True).first()


def _selected_animal(
    request,
    farm: Farm | None,
    group: HerdGroup | None = None,
) -> Animal | None:
    animal_id = _request_value(request, "animal")
    if not animal_id or not farm:
        return None
    animals = Animal.objects.filter(id=animal_id, farm=farm, is_active=True)
    if group:
        animals = animals.filter(current_group=group)
    return animals.first()


def _dashboard_context(request):
    start_date, end_date = _date_range(request)
    farm = _selected_farm(request)
    capabilities = request_capability_codes(request)
    context = {
        "farms": Farm.objects.filter(is_active=True).order_by("name"),
        "selected_farm": farm,
        "start_date": start_date,
        "end_date": end_date,
    }
    if "finance" in capabilities:
        context["pnl"] = get_operating_pnl(
            farm=farm,
            start_date=start_date,
            end_date=end_date,
        )
    if "reproduction" in capabilities:
        attention = daily_reproduction_attention()
        context.update(
            {
                "dry_off": attention["dry_off"][:12],
                "pregnancy_checks": attention["pregnancy_checks"][:12],
            }
        )
    if "health" in capabilities:
        context.update(
            {
                "withdrawals": active_milk_withdrawals()[:12],
                "open_treatments": open_treatments()[:12],
            }
        )
    return context


def home(request):
    return render(request, "dashboard/home.html", _dashboard_context(request))


def pnl_fragment(request):
    return render(request, "dashboard/_pnl.html", _dashboard_context(request))


def action_list_fragment(request):
    return render(request, "dashboard/_actions.html", _dashboard_context(request))


def information_center(request: HttpRequest) -> HttpResponse:
    """Show only traceable official sources until stable provider APIs are available."""
    sources = [
        {
            "title": "Clima y alertas",
            "description": "Pronosticos, alertas y boletines para planificar el trabajo de campo.",
            "meta": "INAMHI | Consulta oficial",
            "url": "https://servicios.inamhi.gob.ec/",
        },
        {
            "title": "Pronostico agrometeorologico",
            "description": (
                "Boletines para revisar lluvia, temperatura y condiciones de la temporada."
            ),
            "meta": "INAMHI | Actualizacion segun publicacion",
            "url": "https://servicios.inamhi.gob.ec/pronostico-agrometeorologico-bisemanal-2026-julio-diciembre/",
        },
        {
            "title": "Campanas sanitarias",
            "description": "Consulta datos publicos de vacunacion contra aftosa y rabia.",
            "meta": "Agrocalidad | Datos Abiertos Ecuador",
            "url": "https://www.datosabiertos.gob.ec/dataset/datos-vacunacion-fiebre-aftosa-mas-rabia/resource/870fcb8b-2b7e-470d-adbd-b690f6996cec",
        },
        {
            "title": "Normativa vigente",
            "description": (
                "Revisa publicaciones y resoluciones oficiales antes de tomar una decision "
                "regulatoria."
            ),
            "meta": "Registro Oficial | Fuente legal",
            "url": "https://www.registroficial.gob.ec/",
        },
    ]
    return render(request, "dashboard/information_center.html", {"sources": sources})


def _finance_context(request: HttpRequest, overrides: dict | None = None) -> dict:
    start_date, end_date = _date_range(request)
    farm = _selected_farm(request)
    group = _selected_group(request, farm)
    animal = _selected_animal(request, farm, group)
    groups = HerdGroup.objects.filter(farm=farm, is_active=True).order_by("name") if farm else []
    animals = Animal.objects.filter(farm=farm, is_active=True).order_by("tag") if farm else []
    if group:
        animals = animals.filter(current_group=group)

    context = {
        "farms": Farm.objects.filter(is_active=True).order_by("name"),
        "groups": groups,
        "animals": animals,
        "selected_farm": farm,
        "selected_group": group,
        "selected_animal": animal,
        "start_date": start_date,
        "end_date": end_date,
        "pnl": get_operating_pnl(
            farm=farm,
            group=group,
            animal=animal,
            start_date=start_date,
            end_date=end_date,
        ),
        "daily_rows": get_daily_pnl(
            farm=farm,
            group=group,
            animal=animal,
            start_date=start_date,
            end_date=end_date,
        )[:14],
        "group_rows": get_group_pnl(farm=farm, start_date=start_date, end_date=end_date),
        "animal_rows": get_animal_pnl(
            farm=farm,
            group=group,
            start_date=start_date,
            end_date=end_date,
        )[:20],
        "cost_rows": get_cost_breakdown(
            farm=farm,
            group=group,
            animal=animal,
            start_date=start_date,
            end_date=end_date,
        ),
        "trace_rows": get_event_trace(
            farm=farm,
            group=group,
            animal=animal,
            start_date=start_date,
            end_date=end_date,
        ),
        "unassigned_rows": get_unassigned_financial_lines(
            farm=farm,
            start_date=start_date,
            end_date=end_date,
        ),
        "snapshot_rows": get_recent_snapshots(farm=farm),
        "expense_form": OperatingExpenseForm(),
        "animal_sale_form": AnimalSaleForm(),
        "finance_message": "",
        "finance_error": "",
    }
    if overrides:
        context.update(overrides)
    return context


def finance_dashboard(request: HttpRequest) -> HttpResponse:
    return render(request, "dashboard/finance.html", _finance_context(request))


def finance_fragment(request: HttpRequest) -> HttpResponse:
    return render(request, "dashboard/_finance_content.html", _finance_context(request))


@require_POST
def finance_close_period(request: HttpRequest) -> HttpResponse:
    start_date, end_date = _date_range(request)
    farm = _selected_farm(request)
    if not farm:
        return render(
            request,
            "dashboard/_finance_content.html",
            _finance_context(request, {"finance_message": "No hay hacienda activa para cerrar."}),
            status=422,
        )

    snapshots = close_operating_period(
        farm=farm,
        group=_selected_group(request, farm),
        animal=_selected_animal(request, farm),
        start_date=start_date,
        end_date=end_date,
        notes="Cierre operativo generado desde Finanzas.",
    )
    return render(
        request,
        "dashboard/_finance_content.html",
        _finance_context(
            request,
            {"finance_message": f"Cierre actualizado: {len(snapshots)} registro(s)."},
        ),
    )


@require_POST
def finance_record_expense(request: HttpRequest) -> HttpResponse:
    form = OperatingExpenseForm(request.POST)
    if not form.is_valid():
        return _finance_error(request, {"expense_form": form})

    data = form.cleaned_data
    try:
        expense = record_operating_expense(
            farm=data["farm"],
            amount=data["amount"],
            cost_type=data["cost_type"],
            cost_date=data["cost_date"],
            group=data["group"],
            animal=data["animal"],
            notes=data["notes"],
        )
    except ValueError as exc:
        return _finance_error(request, {"expense_form": form}, detail=str(exc))

    return render(
        request,
        "dashboard/_finance_content.html",
        _finance_context(
            request,
            {"finance_message": f"Gasto operativo registrado por $ {expense.amount}."},
        ),
    )


@require_POST
def finance_record_animal_sale(request: HttpRequest) -> HttpResponse:
    form = AnimalSaleForm(request.POST)
    if not form.is_valid():
        return _finance_error(request, {"animal_sale_form": form})

    data = form.cleaned_data
    try:
        entry = record_animal_sale(
            farm=data["farm"],
            animal=data["animal"],
            amount=data["amount"],
            sale_date=data["sale_date"],
            notes=data["notes"],
        )
    except ValueError as exc:
        return _finance_error(request, {"animal_sale_form": form}, detail=str(exc))

    message = f"Venta registrada: {entry.animal.tag} por $ {entry.gross_amount}."
    return render(
        request,
        "dashboard/_finance_content.html",
        _finance_context(request, {"finance_message": message}),
    )


def _finance_error(
    request: HttpRequest,
    overrides: dict,
    *,
    detail: str = "",
) -> HttpResponse:
    overrides = {**overrides, "finance_error": detail or "Revisa los datos del formulario."}
    return render(
        request,
        "dashboard/_finance_content.html",
        _finance_context(request, overrides),
        status=422,
    )


def _growth_target(request: HttpRequest) -> Decimal:
    try:
        target = Decimal(_request_value(request, "target") or "500")
    except (InvalidOperation, TypeError):
        return Decimal("500")
    return target if Decimal("1") <= target <= Decimal("2000") else Decimal("500")


def _growth_context(request: HttpRequest, overrides: dict | None = None) -> dict:
    farm = _selected_farm(request)
    group = _selected_group(request, farm)
    target_weight = _growth_target(request)
    metrics = get_growth_metrics(farm=farm, group=group) if farm else []
    gains = [metric.daily_gain for metric in metrics if metric.daily_gain is not None]
    average_daily_gain = None
    if gains:
        average_daily_gain = (sum(gains, Decimal("0")) / len(gains)).quantize(Decimal("0.001"))
    underperformer_threshold = (
        (average_daily_gain * Decimal("0.75")).quantize(Decimal("0.001"))
        if average_daily_gain and average_daily_gain > 0
        else Decimal("0")
    )

    cost_lines: dict = {}
    dated_metrics = [metric for metric in metrics if metric.previous]
    if dated_metrics:
        first_date = min(metric.previous.weighed_on for metric in dated_metrics)
        last_date = max(metric.latest.weighed_on for metric in dated_metrics)
        animal_ids = [metric.animal.id for metric in dated_metrics]
        for line in CostAllocation.objects.filter(
            farm=farm,
            animal_id__in=animal_ids,
            cost_date__range=(first_date, last_date),
        ).values("animal_id", "cost_date", "amount"):
            cost_lines.setdefault(line["animal_id"], []).append(line)

    rows = []
    for metric in metrics:
        direct_cost = Decimal("0")
        if metric.previous:
            direct_cost = sum(
                (
                    line["amount"]
                    for line in cost_lines.get(metric.animal.id, [])
                    if metric.previous.weighed_on <= line["cost_date"] <= metric.latest.weighed_on
                ),
                Decimal("0"),
            )
        cost_per_kg = None
        if metric.gain_kg and metric.gain_kg > 0:
            cost_per_kg = (direct_cost / metric.gain_kg).quantize(Decimal("0.01"))
        rows.append(
            {
                "metric": metric,
                "projected_days": metric.projected_days_to(target_weight),
                "direct_cost": direct_cost,
                "cost_per_kg": cost_per_kg,
                "underperformer": (
                    metric.daily_gain is not None and metric.daily_gain < underperformer_threshold
                ),
            }
        )

    latest_weights = [metric.latest.weight_kg for metric in metrics]
    context = {
        "farms": Farm.objects.filter(is_active=True).order_by("name"),
        "groups": (
            HerdGroup.objects.filter(farm=farm, is_active=True).order_by("name") if farm else []
        ),
        "selected_farm": farm,
        "selected_group": group,
        "target_weight": target_weight,
        "growth_rows": rows,
        "group_rows": summarize_groups(metrics),
        "animals_weighed": len(metrics),
        "average_weight": (
            (sum(latest_weights, Decimal("0")) / len(latest_weights)).quantize(Decimal("0.01"))
            if latest_weights
            else None
        ),
        "average_daily_gain": average_daily_gain,
        "underperformers": sum(1 for row in rows if row["underperformer"]),
        "weight_form": WeightRecordForm(
            farm=farm,
            initial={"farm": farm, "weighed_on": timezone.localdate()},
        ),
        "growth_message": "",
        "growth_error": "",
    }
    if overrides:
        context.update(overrides)
    return context


def growth_dashboard(request: HttpRequest) -> HttpResponse:
    return render(request, "dashboard/growth.html", _growth_context(request))


@require_POST
def growth_record_weight(request: HttpRequest) -> HttpResponse:
    farm = _selected_farm(request)
    form = WeightRecordForm(request.POST, farm=farm)
    if not form.is_valid():
        return render(
            request,
            "dashboard/growth.html",
            _growth_context(
                request,
                {"weight_form": form, "growth_error": "Revisa los datos del pesaje."},
            ),
            status=422,
        )

    data = form.cleaned_data
    record = record_weight(
        farm=data["farm"],
        animal=data["animal"],
        weighed_on=data["weighed_on"],
        weight_kg=data["weight_kg"],
        body_condition_score=data["body_condition_score"],
        scale_identifier=data["scale_identifier"],
        operator=request.user,
        notes=data["notes"],
    )
    return render(
        request,
        "dashboard/growth.html",
        _growth_context(
            request,
            {"growth_message": f"Pesaje guardado: {record.animal.tag}, {record.weight_kg} kg."},
        ),
    )


def _animal_timeline(animal: Animal) -> list[dict]:
    timeline = []

    def add(*, occurred_on, kind: str, title: str, detail: str = "") -> None:
        timeline.append(
            {
                "occurred_on": occurred_on,
                "kind": kind,
                "title": title,
                "detail": detail,
            }
        )

    if animal.birth_date:
        add(occurred_on=animal.birth_date, kind="hato", title="Nacimiento registrado")
    if animal.entry_date:
        add(occurred_on=animal.entry_date, kind="hato", title="Ingreso a la hacienda")

    for row in WeightRecord.objects.filter(animal=animal).select_related("group")[:60]:
        details = [f"{row.weight_kg} kg"]
        if row.body_condition_score is not None:
            details.append(f"condicion corporal {row.body_condition_score}")
        if row.group:
            details.append(row.group.name)
        add(
            occurred_on=row.weighed_on,
            kind="peso",
            title="Pesaje",
            detail=" · ".join(details),
        )

    for row in ReproductionEvent.objects.filter(animal=animal)[:40]:
        detail = row.sire_identifier or row.calf_tag
        add(
            occurred_on=row.occurred_on,
            kind="reproduccion",
            title=row.get_event_type_display(),
            detail=detail,
        )

    for row in Treatment.objects.filter(animal=animal).select_related("input")[:40]:
        detail = row.diagnosis
        if row.input:
            detail = f"{detail} · {row.input.name}"
        add(
            occurred_on=timezone.localtime(row.started_at).date(),
            kind="sanidad",
            title="Tratamiento",
            detail=detail,
        )

    for row in MilkYield.objects.filter(animal=animal).select_related("session")[:40]:
        detail = f"{row.liters} L"
        if row.is_discarded:
            detail = f"{detail} · leche descartada"
        add(
            occurred_on=row.session.milking_date,
            kind="leche",
            title="Ordeño",
            detail=detail,
        )

    for row in InventoryMovement.objects.filter(animal=animal).select_related("input")[:40]:
        add(
            occurred_on=timezone.localtime(row.occurred_at).date(),
            kind="bodega",
            title=row.get_movement_type_display(),
            detail=f"{row.input.name} · {row.quantity} {row.input.unit}",
        )

    for row in RevenueEntry.objects.filter(animal=animal)[:30]:
        add(
            occurred_on=row.revenue_date,
            kind="finanzas",
            title=row.get_revenue_type_display(),
            detail=f"$ {row.gross_amount}",
        )

    for row in CostAllocation.objects.filter(animal=animal)[:30]:
        add(
            occurred_on=row.cost_date,
            kind="finanzas",
            title=row.get_cost_type_display(),
            detail=f"$ {row.amount}" + (f" · {row.notes}" if row.notes else ""),
        )

    return sorted(
        timeline,
        key=lambda item: (item["occurred_on"], item["title"]),
        reverse=True,
    )[:150]


def animal_timeline(request: HttpRequest, pk) -> HttpResponse:
    animal = get_object_or_404(
        Animal.objects.select_related("farm", "current_group", "dam"),
        pk=pk,
    )
    growth = get_animal_growth(animal)
    today = timezone.localdate()
    start_date = animal.birth_date or animal.entry_date or (today - timedelta(days=365))
    return render(
        request,
        "dashboard/animal_timeline.html",
        {
            "animal": animal,
            "growth": growth,
            "timeline": _animal_timeline(animal),
            "pnl": get_operating_pnl(
                farm=animal.farm,
                animal=animal,
                start_date=start_date,
                end_date=today,
            ),
        },
    )


def _is_htmx(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


def _active_queryset(model: type) -> QuerySet:
    queryset = model.objects.all()
    if hasattr(model, "is_active"):
        queryset = queryset.filter(is_active=True)
    return queryset


def _master_data_context(request: HttpRequest, overrides: dict | None = None) -> dict:
    capabilities = request_capability_codes(request)
    has_herd = "herd" in capabilities
    has_inventory = "inventory" in capabilities
    context = {
        "message": "",
        "error": "",
    }
    if has_herd or has_inventory:
        context.update(
            {
                "farms": Farm.objects.filter(is_active=True).order_by("name"),
                "farm_form": FarmForm(),
            }
        )
    if has_herd:
        context.update(
            {
                "groups": HerdGroup.objects.select_related("farm").filter(is_active=True),
                "animals": Animal.objects.select_related("farm", "current_group", "dam").filter(
                    is_active=True
                ),
                "group_form": HerdGroupForm(),
                "animal_form": AnimalForm(),
            }
        )
    if has_inventory:
        context.update(
            {
                "inputs": Input.objects.filter(is_active=True),
                "stock_lots": StockLot.objects.select_related("farm", "input").filter(
                    is_active=True
                ),
                "movements": InventoryMovement.objects.select_related(
                    "farm", "input", "animal", "group"
                )[:20],
                "input_form": InputForm(),
                "stock_lot_form": StockLotForm(),
                "receipt_form": InputReceiptForm(),
                "adjustment_form": StockAdjustmentForm(),
            }
        )
    if overrides:
        context.update(overrides)
    return context


def _render_master_data(
    request: HttpRequest,
    overrides: dict | None = None,
    *,
    status: int = 200,
) -> HttpResponse:
    template_name = (
        "dashboard/_master_data_content.html" if _is_htmx(request) else "dashboard/master_data.html"
    )
    return render(request, template_name, _master_data_context(request, overrides), status=status)


def master_data(request: HttpRequest) -> HttpResponse:
    return _render_master_data(request)


def _create(request: HttpRequest, spec: CrudSpec) -> HttpResponse:
    form = spec.form_class(request.POST)
    if form.is_valid():
        form.save()
        return _render_master_data(request, {"message": spec.success_message})
    return _render_master_data(request, {spec.form_key: form}, status=422)


def _edit(request: HttpRequest, spec: CrudSpec, pk) -> HttpResponse:
    instance = get_object_or_404(_active_queryset(spec.model), pk=pk)
    form = spec.form_class(instance=instance)
    return _render_master_data(request, {spec.form_key: form, spec.edit_key: instance.id})


def _update(request: HttpRequest, spec: CrudSpec, pk) -> HttpResponse:
    instance = get_object_or_404(_active_queryset(spec.model), pk=pk)
    form = spec.form_class(request.POST, instance=instance)
    if form.is_valid():
        form.save()
        return _render_master_data(request, {"message": spec.success_message})
    return _render_master_data(
        request,
        {spec.form_key: form, spec.edit_key: instance.id},
        status=422,
    )


def _deactivate(request: HttpRequest, spec: CrudSpec, pk) -> HttpResponse:
    instance = get_object_or_404(_active_queryset(spec.model), pk=pk)
    if hasattr(instance, "soft_delete"):
        instance.soft_delete()
    else:
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
    return _render_master_data(request, {"message": "Registro desactivado."})


@require_POST
def farm_create(request):
    return _create(request, FARM_SPEC)


def farm_edit(request, pk):
    return _edit(request, FARM_SPEC, pk)


@require_POST
def farm_update(request, pk):
    return _update(request, FARM_SPEC, pk)


@require_POST
def farm_deactivate(request, pk):
    return _deactivate(request, FARM_SPEC, pk)


@require_POST
def group_create(request):
    return _create(request, GROUP_SPEC)


def group_edit(request, pk):
    return _edit(request, GROUP_SPEC, pk)


@require_POST
def group_update(request, pk):
    return _update(request, GROUP_SPEC, pk)


@require_POST
def group_deactivate(request, pk):
    return _deactivate(request, GROUP_SPEC, pk)


@require_POST
def animal_create(request):
    return _create(request, ANIMAL_SPEC)


def animal_edit(request, pk):
    return _edit(request, ANIMAL_SPEC, pk)


@require_POST
def animal_update(request, pk):
    return _update(request, ANIMAL_SPEC, pk)


@require_POST
def animal_deactivate(request, pk):
    return _deactivate(request, ANIMAL_SPEC, pk)


@require_POST
def input_create(request):
    return _create(request, INPUT_SPEC)


def input_edit(request, pk):
    return _edit(request, INPUT_SPEC, pk)


@require_POST
def input_update(request, pk):
    return _update(request, INPUT_SPEC, pk)


@require_POST
def input_deactivate(request, pk):
    return _deactivate(request, INPUT_SPEC, pk)


@require_POST
def stock_lot_create(request):
    return _create(request, STOCK_SPEC)


def stock_lot_edit(request, pk):
    return _edit(request, STOCK_SPEC, pk)


@require_POST
def stock_lot_update(request, pk):
    return _update(request, STOCK_SPEC, pk)


@require_POST
def stock_lot_deactivate(request, pk):
    return _deactivate(request, STOCK_SPEC, pk)


@require_POST
def inventory_receive(request: HttpRequest) -> HttpResponse:
    form = InputReceiptForm(request.POST)
    if not form.is_valid():
        return _render_master_data(
            request,
            {"receipt_form": form, "error": "Revisa los datos de la recepcion."},
            status=422,
        )

    data = form.cleaned_data
    try:
        receipt = receive_input(
            farm=data["farm"],
            input_=data["input"],
            quantity=data["quantity"],
            unit_cost=data["unit_cost"],
            lot_code=data["lot_code"],
            expires_on=data["expires_on"],
            notes=data["notes"],
        )
    except ValueError as exc:
        return _render_master_data(
            request,
            {"receipt_form": form, "error": str(exc)},
            status=422,
        )

    return _render_master_data(
        request,
        {"message": f"Recepcion registrada por $ {receipt.total_cost}."},
    )


@require_POST
def inventory_adjust(request: HttpRequest) -> HttpResponse:
    form = StockAdjustmentForm(request.POST)
    if not form.is_valid():
        return _render_master_data(
            request,
            {"adjustment_form": form, "error": "Revisa los datos del ajuste."},
            status=422,
        )

    data = form.cleaned_data
    try:
        adjustment = adjust_stock(
            farm=data["farm"],
            input_=data["input"],
            quantity_delta=data["quantity_delta"],
            reason=data["reason"],
        )
    except ValueError as exc:
        return _render_master_data(
            request,
            {"adjustment_form": form, "error": str(exc)},
            status=422,
        )

    return _render_master_data(
        request,
        {
            "message": (
                f"Ajuste aplicado: {adjustment.quantity_delta} "
                f"(merma reconocida $ {adjustment.recognized_cost})."
            )
        },
    )
