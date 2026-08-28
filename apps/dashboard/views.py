from datetime import timedelta
from typing import NamedTuple

from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

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
from apps.health.services import active_milk_withdrawals, open_treatments
from apps.herd.models import Animal, Farm, HerdGroup
from apps.inventory.models import Input, InventoryMovement, StockLot
from apps.inventory.services import adjust_stock, receive_input
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
    pnl = get_operating_pnl(farm=farm, start_date=start_date, end_date=end_date)
    attention = daily_reproduction_attention()
    return {
        "farms": Farm.objects.filter(is_active=True).order_by("name"),
        "selected_farm": farm,
        "start_date": start_date,
        "end_date": end_date,
        "pnl": pnl,
        "dry_off": attention["dry_off"][:12],
        "pregnancy_checks": attention["pregnancy_checks"][:12],
        "withdrawals": active_milk_withdrawals()[:12],
        "open_treatments": open_treatments()[:12],
    }


def home(request):
    return render(request, "dashboard/home.html", _dashboard_context(request))


def pnl_fragment(request):
    return render(request, "dashboard/_pnl.html", _dashboard_context(request))


def action_list_fragment(request):
    return render(request, "dashboard/_actions.html", _dashboard_context(request))


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


def _is_htmx(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


def _active_queryset(model: type) -> QuerySet:
    queryset = model.objects.all()
    if hasattr(model, "is_active"):
        queryset = queryset.filter(is_active=True)
    return queryset


def _master_data_context(overrides: dict | None = None) -> dict:
    context = {
        "farms": Farm.objects.filter(is_active=True).order_by("name"),
        "groups": HerdGroup.objects.select_related("farm").filter(is_active=True),
        "animals": Animal.objects.select_related("farm", "current_group", "dam").filter(
            is_active=True
        ),
        "inputs": Input.objects.filter(is_active=True),
        "stock_lots": StockLot.objects.select_related("farm", "input").filter(is_active=True),
        "movements": InventoryMovement.objects.select_related("farm", "input", "animal", "group")[
            :20
        ],
        "farm_form": FarmForm(),
        "group_form": HerdGroupForm(),
        "animal_form": AnimalForm(),
        "input_form": InputForm(),
        "stock_lot_form": StockLotForm(),
        "receipt_form": InputReceiptForm(),
        "adjustment_form": StockAdjustmentForm(),
        "message": "",
        "error": "",
    }
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
    return render(request, template_name, _master_data_context(overrides), status=status)


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
