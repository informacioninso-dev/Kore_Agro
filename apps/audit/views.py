from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .models import AuditEvent


def dashboard(request: HttpRequest) -> HttpResponse:
    events = AuditEvent.objects.select_related("actor")
    action = request.GET.get("action", "")
    model_label = request.GET.get("model", "")
    query = request.GET.get("q", "").strip()
    if action in AuditEvent.Action.values:
        events = events.filter(action=action)
    if model_label:
        events = events.filter(model_label=model_label)
    if query:
        events = events.filter(object_repr__icontains=query)
    model_labels = AuditEvent.objects.order_by("model_label").values_list(
        "model_label", flat=True
    ).distinct()
    return render(
        request,
        "audit/dashboard.html",
        {
            "events": events[:200],
            "model_labels": model_labels,
            "selected_action": action,
            "selected_model": model_label,
            "query": query,
        },
    )
