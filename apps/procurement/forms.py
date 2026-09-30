from decimal import Decimal

from django import forms
from django.db.models import F
from django.utils import timezone

from apps.herd.models import Farm
from apps.inventory.models import Input
from apps.parties.models import Counterparty

from .models import (
    GoodsReceiptLine,
    PurchaseInvoice,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchasePayment,
)


class ProcurementFormMixin:
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


class SupplierForm(ProcurementFormMixin, forms.ModelForm):
    class Meta:
        model = Counterparty
        fields = [
            "legal_name",
            "trade_name",
            "identification_type",
            "identification_number",
            "is_supplier",
            "is_producer",
            "is_customer",
            "is_carrier",
            "email",
            "phone",
            "province",
            "city",
            "address",
            "payment_terms_days",
            "notes",
        ]
        labels = {
            "legal_name": "Razon social o nombre",
            "trade_name": "Nombre comercial",
            "identification_type": "Tipo de identificacion",
            "identification_number": "Identificacion",
            "is_supplier": "Proveedor",
            "is_producer": "Productor",
            "is_customer": "Cliente",
            "is_carrier": "Transportista",
            "email": "Correo",
            "phone": "Telefono",
            "province": "Provincia",
            "city": "Ciudad",
            "address": "Direccion",
            "payment_terms_days": "Plazo de pago (dias)",
            "notes": "Notas",
        }
        widgets = {
            "payment_terms_days": forms.NumberInput(attrs={"min": "0"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and not self.instance.pk:
            self.fields["is_supplier"].initial = True


class PurchaseOrderForm(ProcurementFormMixin, forms.ModelForm):
    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["farm"].queryset = Farm.objects.filter(is_active=True)
        self.fields["supplier"].queryset = Counterparty.objects.filter(
            is_active=True,
            is_supplier=True,
        )
        if farm:
            self.fields["farm"].initial = farm

    class Meta:
        model = PurchaseOrder
        fields = ["farm", "number", "supplier", "ordered_on", "expected_on", "notes"]
        labels = {
            "number": "Numero de orden",
            "supplier": "Proveedor",
            "ordered_on": "Fecha de orden",
            "expected_on": "Entrega esperada",
            "notes": "Condiciones o notas",
        }
        widgets = {
            "farm": forms.HiddenInput(),
            "ordered_on": forms.DateInput(attrs={"type": "date"}),
            "expected_on": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class PurchaseLineForm(ProcurementFormMixin, forms.Form):
    purchase_order = forms.ModelChoiceField(
        queryset=PurchaseOrder.objects.none(),
        label="Orden en borrador",
    )
    input = forms.ModelChoiceField(queryset=Input.objects.none(), label="Insumo")
    quantity = forms.DecimalField(
        label="Cantidad",
        max_digits=14,
        decimal_places=3,
        min_value=Decimal("0.001"),
        widget=forms.NumberInput(attrs={"step": "0.001", "min": "0.001"}),
    )
    unit_cost = forms.DecimalField(
        label="Costo unitario",
        max_digits=12,
        decimal_places=4,
        min_value=Decimal("0"),
        widget=forms.NumberInput(attrs={"step": "0.0001", "min": "0"}),
    )
    tax_rate = forms.DecimalField(
        label="Impuesto (%)",
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        initial=Decimal("0"),
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100"}),
    )

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if farm:
            self.fields["purchase_order"].queryset = PurchaseOrder.objects.filter(
                farm=farm,
                status=PurchaseOrder.Status.DRAFT,
            ).select_related("supplier")
        self.fields["input"].queryset = Input.objects.filter(is_active=True)


class PurchaseOrderActionForm(ProcurementFormMixin, forms.Form):
    class Action:
        SUBMIT = "submit"
        APPROVE = "approve"
        REJECT = "reject"
        CANCEL = "cancel"

    purchase_order = forms.ModelChoiceField(
        queryset=PurchaseOrder.objects.none(),
        label="Orden",
    )
    action = forms.ChoiceField(label="Accion", choices=())
    rejection_reason = forms.CharField(label="Motivo del rechazo", max_length=255, required=False)

    def __init__(self, *args, farm=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = []
        statuses = set()
        if user and user.has_perm("procurement.submit_purchaseorder"):
            choices.append((self.Action.SUBMIT, "Enviar para aprobacion"))
            statuses.add(PurchaseOrder.Status.DRAFT)
        if user and user.has_perm("procurement.approve_purchaseorder"):
            choices.extend(
                (
                    (self.Action.APPROVE, "Aprobar y emitir"),
                    (self.Action.REJECT, "Rechazar"),
                )
            )
            statuses.add(PurchaseOrder.Status.PENDING_APPROVAL)
        if user and user.has_perm("procurement.change_purchaseorder"):
            choices.append((self.Action.CANCEL, "Cancelar orden"))
            statuses.update(
                {
                    PurchaseOrder.Status.DRAFT,
                    PurchaseOrder.Status.PENDING_APPROVAL,
                    PurchaseOrder.Status.ORDERED,
                }
            )
        self.fields["action"].choices = choices
        if farm:
            self.fields["purchase_order"].queryset = PurchaseOrder.objects.filter(
                farm=farm,
                status__in=statuses,
            ).select_related("supplier")

    def clean(self):
        data = super().clean()
        rejecting_without_reason = data.get("action") == self.Action.REJECT and not data.get(
            "rejection_reason", ""
        ).strip()
        if rejecting_without_reason:
            self.add_error("rejection_reason", "Indica el motivo del rechazo.")
        return data


class PurchaseReceiptForm(ProcurementFormMixin, forms.Form):
    order_line = forms.ModelChoiceField(
        queryset=PurchaseOrderLine.objects.none(),
        label="Insumo pendiente",
    )
    quantity = forms.DecimalField(
        label="Cantidad recibida",
        max_digits=14,
        decimal_places=3,
        min_value=Decimal("0.001"),
        widget=forms.NumberInput(attrs={"step": "0.001", "min": "0.001"}),
    )
    received_at = forms.DateTimeField(
        label="Fecha y hora",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    lot_code = forms.CharField(label="Lote del proveedor", max_length=80, required=False)
    expires_on = forms.DateField(
        label="Caducidad",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    supplier_document = forms.CharField(
        label="Factura o documento",
        max_length=80,
        required=False,
    )
    notes = forms.CharField(label="Notas", max_length=255, required=False)

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["received_at"].initial = timezone.localtime().strftime("%Y-%m-%dT%H:%M")
        if farm:
            self.fields["order_line"].queryset = (
                PurchaseOrderLine.objects.filter(
                    purchase_order__farm=farm,
                    purchase_order__status__in=(
                        PurchaseOrder.Status.ORDERED,
                        PurchaseOrder.Status.PARTIAL,
                    ),
                    quantity_received__lt=F("quantity_ordered"),
                )
                .select_related("purchase_order__supplier", "input")
                .order_by("purchase_order__ordered_on", "created_at")
            )


class PurchaseInvoiceForm(ProcurementFormMixin, forms.Form):
    purchase_order = forms.ModelChoiceField(
        queryset=PurchaseOrder.objects.none(),
        label="Orden recibida",
    )
    invoice_number = forms.CharField(label="Numero de factura", max_length=80)
    issued_on = forms.DateField(
        label="Fecha de emision",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    due_on = forms.DateField(
        label="Fecha de vencimiento",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    notes = forms.CharField(label="Notas", max_length=255, required=False)

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["issued_on"].initial = timezone.localdate()
        if farm:
            self.fields["purchase_order"].queryset = PurchaseOrder.objects.filter(
                farm=farm,
                status=PurchaseOrder.Status.RECEIVED,
                invoice__isnull=True,
            ).select_related("supplier")


class PurchasePaymentForm(ProcurementFormMixin, forms.Form):
    invoice = forms.ModelChoiceField(queryset=PurchaseInvoice.objects.none(), label="Factura")
    amount = forms.DecimalField(
        label="Valor pagado",
        max_digits=16,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
    )
    paid_on = forms.DateField(
        label="Fecha de pago",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    method = forms.ChoiceField(label="Forma de pago", choices=PurchasePayment.Method.choices)
    reference = forms.CharField(label="Referencia", max_length=100, required=False)
    notes = forms.CharField(label="Notas", max_length=255, required=False)

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["paid_on"].initial = timezone.localdate()
        if farm:
            self.fields["invoice"].queryset = PurchaseInvoice.objects.filter(
                purchase_order__farm=farm,
                status__in=(PurchaseInvoice.Status.PENDING, PurchaseInvoice.Status.PARTIAL),
            ).select_related("purchase_order__supplier")


class PurchaseReturnForm(ProcurementFormMixin, forms.Form):
    receipt_line = forms.ModelChoiceField(
        queryset=GoodsReceiptLine.objects.none(),
        label="Recepcion",
    )
    quantity = forms.DecimalField(
        label="Cantidad a devolver",
        max_digits=14,
        decimal_places=3,
        min_value=Decimal("0.001"),
        widget=forms.NumberInput(attrs={"step": "0.001", "min": "0.001"}),
    )
    returned_at = forms.DateTimeField(
        label="Fecha y hora",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    reason = forms.CharField(label="Motivo", max_length=255)
    credit_document = forms.CharField(
        label="Nota de credito",
        max_length=80,
        required=False,
    )

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["returned_at"].initial = timezone.localtime().strftime(
                "%Y-%m-%dT%H:%M"
            )
        if farm:
            self.fields["receipt_line"].queryset = GoodsReceiptLine.objects.filter(
                receipt__purchase_order__farm=farm,
                inventory_movement__stock_lot__quantity_on_hand__gt=0,
            ).select_related("receipt__purchase_order", "order_line__input")
