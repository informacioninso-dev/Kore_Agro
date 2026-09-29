from functools import wraps

from django.shortcuts import render
from django_tenants.utils import get_public_schema_name

from apps.tenants.models import Client

from .services import active_profile_codes, enabled_capability_codes


def _request_organization(request) -> Client | None:
    organization = getattr(request, "tenant", None)
    if not organization or organization.schema_name == get_public_schema_name():
        return None
    return organization


def request_capability_codes(request) -> frozenset[str]:
    cached = getattr(request, "_kore_capability_codes", None)
    if cached is not None:
        return cached

    organization = _request_organization(request)
    codes = frozenset(enabled_capability_codes(organization)) if organization else frozenset()
    request._kore_capability_codes = codes
    return codes


def request_profile_codes(request) -> frozenset[str]:
    cached = getattr(request, "_kore_profile_codes", None)
    if cached is not None:
        return cached

    organization = _request_organization(request)
    codes = frozenset(active_profile_codes(organization)) if organization else frozenset()
    request._kore_profile_codes = codes
    return codes


def capability_required(*required_codes: str, match_any: bool = False):
    required = frozenset(required_codes)

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            enabled = request_capability_codes(request)
            allowed = bool(required & enabled) if match_any else required.issubset(enabled)
            if allowed:
                return view(request, *args, **kwargs)
            return render(
                request,
                "dashboard/capability_denied.html",
                {"required_capabilities": sorted(required)},
                status=403,
            )

        return wrapped

    return decorator
