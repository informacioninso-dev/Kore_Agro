from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.herd.models import Farm
from apps.parties.models import Counterparty

from .forms import (
    PurchaseLineForm,
    PurchaseOrderActionForm,
    PurchaseOrderForm,
    PurchaseReceiptForm,
    SupplierForm,
)
from .models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder
from .services import (
    add_purchase_line,
    cancel_purchase_order,
    place_purchase_order,
    receive_purchase_line,
)


def _selected_farm(request: HttpRequest) -> Farm | None:
    farm_id = request.POST.get("farm") or request.GET.get("farm")
    if farm_id:
        return Farm.objects.filter(pk=farm_id, is_active=True).first()
    return Farm.objects.filter(is_active=True).order_by("name").first()


def _error_text(exc: ValidationError) -> str:
    return " ".join(exc.messages)


def _next_order_number() -> str:
    prefix = timezone.localdate().strftime("OC-%Y%m%d")
    sequence = PurchaseOrder.objects.filter(number__startswith=prefix).count() + 1
    return f"{prefix}-{sequence:03d}"


def _procurement_context(
    request: HttpRequest,
    *,
    farm: Farm | None = None,
    overrides: dict | None = None,
) -> dict:
    selected_farm = farm or _selected_farm(request)
    suppliers = Counterparty.objects.filter(is_active=True, is_supplier=True)
    orders = PurchaseOrder.objects.none()
    receipts = GoodsReceipt.objects.none()
    open_orders = 0
    pending_units = Decimal("0")
    committed_value = Decimal("0")
    month_received = Decimal("0")
    if selected_farm:
        orders = (
            PurchaseOrder.objects.filter(farm=selected_farm)
            .select_related("supplier")
            .prefetch_related("lines__input")[:30]
        )
        receipts = (
            GoodsReceipt.objects.filter(purchase_order__farm=selected_farm)
            .select_related("purchase_order__supplier")
            .prefetch_related("lines__order_line__input")[:20]
        )
        active_orders = [
            order
            for order in orders
            if order.status
            in {
                PurchaseOrder.Status.DRAFT,
                PurchaseOrder.Status.ORDERED,
                PurchaseOrder.Status.PARTIAL,
            }
        ]
        open_orders = len(active_orders)
        committed_value = sum((order.total_amount for order in active_orders), Decimal("0"))
        pending_units = sum(
            (line.remaining_quantity for order in active_orders for line in order.lines.all()),
            Decimal("0"),
        )
        today = timezone.localdate()
        line_total = ExpressionWrapper(
            F("quantity") * F("unit_cost"),
            output_field=DecimalField(max_digits=18, decimal_places=4),
        )
        month_received = (
            GoodsReceiptLine.objects.filter(
                receipt__purchase_order__farm=selected_farm,
                receipt__received_at__year=today.year,
                receipt__received_at__month=today.month,
            ).aggregate(total=Sum(line_total))["total"]
            or Decimal("0")
        )

    context = {
        "farms": Farm.objects.filter(is_active=True).order_by("name"),
        "selected_farm": selected_farm,
        "suppliers": suppliers,
        "orders": orders,
        "receipts": receipts,
        "supplier_count": suppliers.count(),
        "open_orders": open_orders,
        "pending_units": pending_units,
        "committed_value": committed_value,
        "month_received": month_received,
        "supplier_form": SupplierForm(),
        "order_form": PurchaseOrderForm(
            farm=selected_farm,
            initial={
                "farm": selected_farm,
                "number": _next_order_number(),
                "ordered_on": timezone.localdate(),
            },
        ),
        "line_form": PurchaseLineForm(farm=selected_farm),
        "action_form": PurchaseOrderActionForm(farm=selected_farm),
        "receipt_form": PurchaseReceiptForm(farm=selected_farm),
        "supplier_edit_id": None,
        "procurement_message": "",
        "procurement_error": "",
    }
    if overrides:
        context.update(overrides)
    return context


def dashboard(request: HttpRequest) -> HttpResponse:
    return render(request, "procurement/dashboard.html", _procurement_context(request))


@require_POST
def supplier_create(request: HttpRequest) -> HttpResponse:
    farm = _selected_farm(request)
    form = SupplierForm(request.POST)
    if not form.is_valid():
        return _render_error(request, farm, {"supplier_form": form}, "Revisa el proveedor.")
    supplier = form.save()
    return _render_success(request, farm, f"Proveedor {supplier.display_name} creado.")


def supplier_edit(request: HttpRequest, pk) -> HttpResponse:
    supplier = get_object_or_404(Counterparty, pk=pk, is_active=True)
    return render(
        request,
        "procurement/dashboard.html",
        _procurement_context(
            request,
            overrides={
                "supplier_form": SupplierForm(instance=supplier),
                "supplier_edit_id": supplier.id,
            },
        ),
    )


@require_POST
def supplier_update(request: HttpRequest, pk) -> HttpResponse:
    supplier = get_object_or_404(Counterparty, pk=pk, is_active=True)
    farm = _selected_farm(request)
    form = SupplierForm(request.POST, instance=supplier)
    if not form.is_valid():
        return _render_error(
            request,
            farm,
            {"supplier_form": form, "supplier_edit_id": supplier.id},
            "Revisa el proveedor.",
        )
    supplier = form.save()
    return _render_success(request, farm, f"Proveedor {supplier.display_name} actualizado.")


@require_POST
def supplier_deactivate(request: HttpRequest, pk) -> HttpResponse:
    supplier = get_object_or_404(Counterparty, pk=pk, is_active=True)
    farm = _selected_farm(request)
    if supplier.purchase_orders.filter(
        status__in=(
            PurchaseOrder.Status.DRAFT,
            PurchaseOrder.Status.ORDERED,
            PurchaseOrder.Status.PARTIAL,
        )
    ).exists():
        return _render_error(
            request,
            farm,
            {},
            "Cancela o recibe las ordenes abiertas antes de desactivar al proveedor.",
        )
    supplier.soft_delete()
    return _render_success(request, farm, f"Proveedor {supplier.display_name} desactivado.")


@require_POST
def order_create(request: HttpRequest) -> HttpResponse:
    farm = _selected_farm(request)
    form = PurchaseOrderForm(request.POST, farm=farm)
    if not form.is_valid():
        return _render_error(request, farm, {"order_form": form}, "Revisa la orden.")
    order = form.save()
    return _render_success(request, order.farm, f"Orden {order.number} creada en borrador.")


@require_POST
def line_create(request: HttpRequest) -> HttpResponse:
    farm = _selected_farm(request)
    form = PurchaseLineForm(request.POST, farm=farm)
    if not form.is_valid():
        return _render_error(request, farm, {"line_form": form}, "Revisa el insumo.")
    data = form.cleaned_data
    try:
        line = add_purchase_line(
            purchase_order=data["purchase_order"],
            input_=data["input"],
            quantity=data["quantity"],
            unit_cost=data["unit_cost"],
            tax_rate=data["tax_rate"],
        )
    except ValidationError as exc:
        return _render_error(request, farm, {"line_form": form}, _error_text(exc))
    return _render_success(
        request,
        line.purchase_order.farm,
        f"{line.input.name} agregado a {line.purchase_order.number}.",
    )


@require_POST
def order_action(request: HttpRequest) -> HttpResponse:
    farm = _selected_farm(request)
    form = PurchaseOrderActionForm(request.POST, farm=farm)
    if not form.is_valid():
        return _render_error(request, farm, {"action_form": form}, "Revisa la accion.")
    try:
        if form.cleaned_data["action"] == PurchaseOrderActionForm.Action.PLACE:
            order = place_purchase_order(form.cleaned_data["purchase_order"])
            message = f"Orden {order.number} emitida al proveedor."
        else:
            order = cancel_purchase_order(form.cleaned_data["purchase_order"])
            message = f"Orden {order.number} cancelada."
    except ValidationError as exc:
        return _render_error(request, farm, {"action_form": form}, _error_text(exc))
    return _render_success(request, order.farm, message)


@require_POST
def receipt_create(request: HttpRequest) -> HttpResponse:
    farm = _selected_farm(request)
    form = PurchaseReceiptForm(request.POST, farm=farm)
    if not form.is_valid():
        return _render_error(request, farm, {"receipt_form": form}, "Revisa la recepcion.")
    data = form.cleaned_data
    try:
        result = receive_purchase_line(
            order_line=data["order_line"],
            quantity=data["quantity"],
            received_at=data["received_at"],
            lot_code=data["lot_code"],
            expires_on=data["expires_on"],
            supplier_document=data["supplier_document"],
            notes=data["notes"],
        )
    except ValidationError as exc:
        return _render_error(request, farm, {"receipt_form": form}, _error_text(exc))
    order = result.receipt.purchase_order
    return _render_success(
        request,
        order.farm,
        f"Recepcion de {result.line.quantity} registrada en {order.number} e inventario.",
    )


def _render_error(
    request: HttpRequest,
    farm: Farm | None,
    overrides: dict,
    message: str,
) -> HttpResponse:
    return render(
        request,
        "procurement/dashboard.html",
        _procurement_context(
            request,
            farm=farm,
            overrides={**overrides, "procurement_error": message},
        ),
        status=422,
    )


def _render_success(request: HttpRequest, farm: Farm | None, message: str) -> HttpResponse:
    return render(
        request,
        "procurement/dashboard.html",
        _procurement_context(
            request,
            farm=farm,
            overrides={"procurement_message": message},
        ),
    )
