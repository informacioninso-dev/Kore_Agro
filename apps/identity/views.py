from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render
from django.urls import reverse


def login_view(request):
    if request.user.is_authenticated:
        return redirect(request.GET.get("next") or reverse("dashboard:home"))

    form = AuthenticationForm(request, data=request.POST or None)
    form.fields["username"].widget.attrs.update(
        {"placeholder": "Ej. dueno", "autocomplete": "username"}
    )
    form.fields["password"].widget.attrs.update(
        {"placeholder": "Tu contraseña", "autocomplete": "current-password"}
    )
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect(request.POST.get("next") or reverse("dashboard:home"))

    context = {"form": form, "next": request.GET.get("next", "")}
    return render(request, "identity/login.html", context)
