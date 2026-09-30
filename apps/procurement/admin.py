from django.contrib import admin

from .models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseInvoice,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchasePayment,
    PurchaseReturn,
)


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("number", "farm", "supplier", "ordered_on", "status")
    list_filter = ("farm", "status", "ordered_on")
    search_fields = ("number", "supplier__legal_name", "supplier__identification_number")
    date_hierarchy = "ordered_on"
    inlines = [PurchaseOrderLineInline]


class GoodsReceiptLineInline(admin.TabularInline):
    model = GoodsReceiptLine
    extra = 0
    readonly_fields = ("inventory_movement",)


@admin.register(GoodsReceipt)
class GoodsReceiptAdmin(admin.ModelAdmin):
    list_display = ("purchase_order", "received_at", "supplier_document")
    list_filter = ("purchase_order__farm", "received_at")
    search_fields = ("purchase_order__number", "supplier_document")
    date_hierarchy = "received_at"
    inlines = [GoodsReceiptLineInline]


class PurchasePaymentInline(admin.TabularInline):
    model = PurchasePayment
    extra = 0


@admin.register(PurchaseInvoice)
class PurchaseInvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "purchase_order", "due_on", "total_amount", "status")
    list_filter = ("status", "due_on", "purchase_order__farm")
    search_fields = ("invoice_number", "purchase_order__number")
    date_hierarchy = "issued_on"
    inlines = [PurchasePaymentInline]


@admin.register(PurchaseReturn)
class PurchaseReturnAdmin(admin.ModelAdmin):
    list_display = ("receipt_line", "returned_at", "quantity", "credit_document")
    list_filter = ("returned_at", "receipt_line__receipt__purchase_order__farm")
    search_fields = ("receipt_line__receipt__purchase_order__number", "credit_document")
    date_hierarchy = "returned_at"
