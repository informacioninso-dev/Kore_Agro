from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django_tenants.utils import get_public_schema_name

from apps.tenants.models import Client

from .forms import CapabilityDefinitionForm, OrganizationForm, ProfileDefinitionForm
from .models import CapabilityDefinition, ProfileDefinition
from .services import provision_owner


def platform_superuser_required(view):
    @wraps(view)
    def wrapped(request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('platform:login')}?next={request.get_full_path()}")
        if not request.user.is_active or not request.user.is_superuser:
            raise PermissionDenied("Este panel es exclusivo para administradores de plataforma.")
        return view(request, *args, **kwargs)

    return wrapped


def platform_login(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect("platform:dashboard")
        raise PermissionDenied("Este panel es exclusivo para administradores de plataforma.")

    form = AuthenticationForm(request, data=request.POST or None)
    for field in form.fields.values():
        field.widget.attrs["class"] = "platform-input"
    form.fields["username"].widget.attrs.update(
        {"placeholder": "Usuario BINNSO", "autocomplete": "username"}
    )
    form.fields["password"].widget.attrs.update(
        {"placeholder": "Contraseña", "autocomplete": "current-password"}
    )
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if not user.is_superuser:
            form.add_error(None, "Este usuario no administra la plataforma.")
        else:
            login(request, user)
            next_url = request.POST.get("next", "")
            if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                next_url = reverse("platform:dashboard")
            return redirect(next_url)

    return render(
        request,
        "platform/login.html",
        {"form": form, "next": request.GET.get("next", "")},
    )


@require_POST
def platform_logout(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("platform:login")


def _organizations():
    return (
        Client.objects.exclude(schema_name=get_public_schema_name())
        .prefetch_related(
            "domains",
            "profile_assignments__profile",
            "capability_assignments__capability",
        )
        .order_by("name")
    )


def _commercial_status(organization: Client) -> tuple[str, str]:
    if organization.on_trial:
        return "trial", "Prueba"
    if organization.paid_until and organization.paid_until < timezone.localdate():
        return "expired", "Vencida"
    return "active", "Activa"


def _organization_row(organization: Client) -> dict:
    primary_domain = next(
        (domain.domain for domain in organization.domains.all() if domain.is_primary),
        "",
    )
    profiles = [
        assignment.profile
        for assignment in organization.profile_assignments.all()
        if assignment.is_active
    ]
    capabilities = [
        assignment.capability
        for assignment in organization.capability_assignments.all()
        if assignment.is_available
    ]
    status, status_label = _commercial_status(organization)
    return {
        "organization": organization,
        "domain": primary_domain,
        "profiles": profiles,
        "capabilities": capabilities,
        "status": status,
        "status_label": status_label,
    }


@platform_superuser_required
def dashboard(request: HttpRequest) -> HttpResponse:
    organizations = list(_organizations())
    rows = [_organization_row(organization) for organization in organizations]
    today = timezone.localdate()
    profile_summary = ProfileDefinition.objects.filter(is_active=True).annotate(
        organization_count=Count(
            "organization_assignments",
            filter=Q(organization_assignments__is_active=True),
            distinct=True,
        )
    )
    return render(
        request,
        "platform/dashboard.html",
        {
            "organization_count": len(rows),
            "active_count": sum(row["status"] == "active" for row in rows),
            "trial_count": sum(row["status"] == "trial" for row in rows),
            "expiring_count": sum(
                bool(
                    row["organization"].paid_until
                    and today <= row["organization"].paid_until <= today + timedelta(days=30)
                )
                for row in rows
            ),
            "profile_count": ProfileDefinition.objects.filter(is_active=True).count(),
            "capability_count": CapabilityDefinition.objects.filter(is_active=True).count(),
            "recent_rows": sorted(
                rows,
                key=lambda row: row["organization"].created_at,
                reverse=True,
            )[:8],
            "profile_summary": profile_summary,
        },
    )


@platform_superuser_required
def organization_list(request: HttpRequest) -> HttpResponse:
    queryset = _organizations()
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    profile_code = request.GET.get("profile", "").strip()
    today = timezone.localdate()
    if query:
        queryset = queryset.filter(
            Q(name__icontains=query)
            | Q(legal_name__icontains=query)
            | Q(ruc__icontains=query)
            | Q(schema_name__icontains=query)
            | Q(domains__domain__icontains=query)
        ).distinct()
    if status == "trial":
        queryset = queryset.filter(on_trial=True)
    elif status == "expired":
        queryset = queryset.filter(on_trial=False, paid_until__lt=today)
    elif status == "active":
        queryset = queryset.filter(on_trial=False).filter(
            Q(paid_until__isnull=True) | Q(paid_until__gte=today)
        )
    if profile_code:
        queryset = queryset.filter(
            profile_assignments__is_active=True,
            profile_assignments__profile__code=profile_code,
        ).distinct()
    return render(
        request,
        "platform/organization_list.html",
        {
            "rows": [_organization_row(organization) for organization in queryset],
            "profiles": ProfileDefinition.objects.filter(is_active=True),
            "query": query,
            "selected_status": status,
            "selected_profile": profile_code,
        },
    )


@platform_superuser_required
def organization_create(request: HttpRequest) -> HttpResponse:
    form = OrganizationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        owner = {
            "username": form.cleaned_data["owner_username"],
            "email": form.cleaned_data["owner_email"],
            "password": form.cleaned_data["owner_password"],
        }
        organization = form.save()
        provision_owner(organization, **owner)
        messages.success(
            request,
            f"{organization.name} fue creada con su esquema, dominio y propietario.",
        )
        return redirect("platform:organization_edit", pk=organization.pk)
    return render(
        request,
        "platform/organization_form.html",
        {"form": form, "organization": None},
        status=422 if request.method == "POST" else 200,
    )


@platform_superuser_required
def organization_edit(request: HttpRequest, pk: int) -> HttpResponse:
    organization = get_object_or_404(
        Client.objects.exclude(schema_name=get_public_schema_name()),
        pk=pk,
    )
    form = OrganizationForm(request.POST or None, instance=organization)
    if request.method == "POST" and form.is_valid():
        organization = form.save()
        messages.success(request, f"Configuracion de {organization.name} actualizada.")
        return redirect("platform:organization_edit", pk=organization.pk)
    return render(
        request,
        "platform/organization_form.html",
        {"form": form, "organization": organization},
        status=422 if request.method == "POST" else 200,
    )


@platform_superuser_required
def catalog(request: HttpRequest) -> HttpResponse:
    capabilities = CapabilityDefinition.objects.prefetch_related("compatible_profiles")
    return render(
        request,
        "platform/catalog.html",
        {
            "profiles": ProfileDefinition.objects.annotate(
                organization_count=Count(
                    "organization_assignments",
                    filter=Q(organization_assignments__is_active=True),
                )
            ),
            "capabilities": capabilities,
        },
    )


@platform_superuser_required
def profile_create(request: HttpRequest) -> HttpResponse:
    return _catalog_form(request, ProfileDefinitionForm(), "Perfil nuevo")


@platform_superuser_required
def profile_edit(request: HttpRequest, pk: int) -> HttpResponse:
    profile = get_object_or_404(ProfileDefinition, pk=pk)
    return _catalog_form(
        request,
        ProfileDefinitionForm(instance=profile),
        "Editar perfil",
        instance=profile,
    )


@platform_superuser_required
def capability_create(request: HttpRequest) -> HttpResponse:
    return _catalog_form(request, CapabilityDefinitionForm(), "Capacidad nueva")


@platform_superuser_required
def capability_edit(request: HttpRequest, pk: int) -> HttpResponse:
    capability = get_object_or_404(CapabilityDefinition, pk=pk)
    return _catalog_form(
        request,
        CapabilityDefinitionForm(instance=capability),
        "Editar capacidad",
        instance=capability,
    )


def _catalog_form(request, form, title: str, *, instance=None) -> HttpResponse:
    form_class = form.__class__
    if request.method == "POST":
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            label = title.replace("Editar ", "").replace(" nuevo", "")
            messages.success(request, f"{label} guardado.")
            return redirect("platform:catalog")
    return render(
        request,
        "platform/catalog_form.html",
        {"form": form, "form_title": title},
        status=422 if request.method == "POST" else 200,
    )
