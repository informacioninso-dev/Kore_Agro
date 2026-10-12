from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from apps.common.security import (
    clear_login_failures,
    login_is_blocked,
    register_login_failure,
    safe_next_url,
)

from .access import ensure_role_groups


@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return redirect(
            safe_next_url(request, request.GET.get("next"), reverse("dashboard:home"))
        )

    username = request.POST.get("username", "")
    form = AuthenticationForm(request, data=request.POST or None)
    form.fields["username"].widget.attrs.update(
        {"placeholder": "Ej. dueno", "autocomplete": "username"}
    )
    form.fields["password"].widget.attrs.update(
        {"placeholder": "Tu contraseña", "autocomplete": "current-password"}
    )
    status = 200
    if request.method == "POST":
        if login_is_blocked(request, username):
            form.add_error(None, "Demasiados intentos. Espera unos minutos antes de reintentar.")
            status = 429
        elif form.is_valid():
            ensure_role_groups()
            login(request, form.get_user())
            clear_login_failures(request, username)
            return redirect(
                safe_next_url(
                    request,
                    request.POST.get("next"),
                    reverse("dashboard:home"),
                )
            )
        elif register_login_failure(request, username):
            form.add_error(None, "Demasiados intentos. Espera unos minutos antes de reintentar.")
            status = 429

    context = {"form": form, "next": request.GET.get("next", "")}
    return render(request, "identity/login.html", context, status=status)
