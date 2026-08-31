from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import AnimalMovementGuideForm, MilkInvoiceDraftForm
from .models import AnimalMovementGuide, MilkInvoice
from .services import SRIConfigurationError, create_draft_milk_invoice, request_sri_submission


def _context(overrides: dict | None = None) -> dict:
    context = {
        "invoice_form": MilkInvoiceDraftForm(),
        "guide_form": AnimalMovementGuideForm(),
        "invoices": MilkInvoice.objects.select_related("farm")[:20],
        "guides": AnimalMovementGuide.objects.select_related("farm")
        .prefetch_related("animals")[:20],
        "message": "",
        "error": "",
    }
    if overrides:
        context.update(overrides)
    return context


def billing_dashboard(request: HttpRequest) -> HttpResponse:
    return render(request, "billing/dashboard.html", _context())


@require_POST
def invoice_create(request: HttpRequest) -> HttpResponse:
    form = MilkInvoiceDraftForm(request.POST)
    if form.is_valid():
        try:
            invoice = create_draft_milk_invoice(**form.cleaned_data)
        except ValidationError as exc:
            return render(
                request,
                "billing/dashboard.html",
                _context({"invoice_form": form, "error": exc.messages[0]}),
                status=422,
            )
        return render(
            request,
            "billing/dashboard.html",
            _context({"message": f"Factura borrador creada para {invoice.buyer_name}."}),
        )
    return render(request, "billing/dashboard.html", _context({"invoice_form": form}), status=422)


@require_POST
def invoice_submit(request: HttpRequest, pk) -> HttpResponse:
    invoice = MilkInvoice.objects.get(pk=pk)
    try:
        request_sri_submission(invoice)
    except SRIConfigurationError as exc:
        return render(
            request,
            "billing/dashboard.html",
            _context({"error": exc.messages[0]}),
            status=422,
        )
    return redirect(reverse("billing:dashboard"))


@require_POST
def guide_create(request: HttpRequest) -> HttpResponse:
    form = AnimalMovementGuideForm(request.POST)
    if form.is_valid():
        guide = form.save()
        return render(
            request,
            "billing/dashboard.html",
            _context({"message": f"Guia borrador creada para {guide.destination}."}),
        )
    return render(request, "billing/dashboard.html", _context({"guide_form": form}), status=422)
