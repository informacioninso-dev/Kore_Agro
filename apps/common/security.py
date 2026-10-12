from hashlib import sha256

from django.conf import settings
from django.core.cache import cache
from django.utils.http import url_has_allowed_host_and_scheme


def safe_next_url(request, candidate: str | None, fallback: str) -> str:
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return fallback


def _login_keys(request, username: str) -> tuple[str, str]:
    tenant = getattr(getattr(request, "tenant", None), "schema_name", "public")
    remote_address = request.META.get("REMOTE_ADDR", "unknown")
    identity = f"{tenant}|{remote_address}|{username.strip().casefold()}"
    address = f"{tenant}|{remote_address}"
    return (
        f"security:login:identity:{sha256(identity.encode()).hexdigest()}",
        f"security:login:address:{sha256(address.encode()).hexdigest()}",
    )


def login_is_blocked(request, username: str) -> bool:
    identity_key, address_key = _login_keys(request, username)
    return (
        int(cache.get(identity_key, 0)) >= settings.LOGIN_FAILURE_LIMIT
        or int(cache.get(address_key, 0)) >= settings.LOGIN_IP_FAILURE_LIMIT
    )


def register_login_failure(request, username: str) -> bool:
    identity_key, address_key = _login_keys(request, username)
    identity_attempts = _increment_with_timeout(
        identity_key,
        settings.LOGIN_FAILURE_WINDOW_SECONDS,
    )
    address_attempts = _increment_with_timeout(
        address_key,
        settings.LOGIN_FAILURE_WINDOW_SECONDS,
    )
    blocked = (
        identity_attempts >= settings.LOGIN_FAILURE_LIMIT
        or address_attempts >= settings.LOGIN_IP_FAILURE_LIMIT
    )
    if blocked:
        cache.set(identity_key, identity_attempts, settings.LOGIN_LOCKOUT_SECONDS)
        cache.set(address_key, address_attempts, settings.LOGIN_LOCKOUT_SECONDS)
    return blocked


def clear_login_failures(request, username: str) -> None:
    identity_key, _ = _login_keys(request, username)
    cache.delete(identity_key)


def _increment_with_timeout(key: str, timeout: int) -> int:
    if cache.add(key, 1, timeout):
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout)
        return 1


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        admin_inline = " 'unsafe-inline'" if request.path.startswith("/admin/") else ""
        response.headers.setdefault(
            "Content-Security-Policy",
            "; ".join(
                (
                    "default-src 'self'",
                    f"script-src 'self'{admin_inline}",
                    "style-src 'self' 'unsafe-inline'",
                    "img-src 'self' data:",
                    "font-src 'self'",
                    "connect-src 'self'",
                    "manifest-src 'self'",
                    "object-src 'none'",
                    "base-uri 'self'",
                    "frame-ancestors 'none'",
                    "form-action 'self'",
                )
            ),
        )
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        return response
