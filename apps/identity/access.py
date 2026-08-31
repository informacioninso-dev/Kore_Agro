from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied

ROLE_OWNER = "owner"
ROLE_MANAGER = "manager"
ROLE_FIELD_WORKER = "field_worker"

MANAGEMENT_ROLES = (ROLE_OWNER, ROLE_MANAGER)
FIELD_ROLES = (ROLE_OWNER, ROLE_MANAGER, ROLE_FIELD_WORKER)
ROLE_LABELS = {
    ROLE_OWNER: "Propietario",
    ROLE_MANAGER: "Administrador",
    ROLE_FIELD_WORKER: "Mayordomo",
}


def ensure_role_groups():
    from django.contrib.auth.models import Group

    for role in ROLE_LABELS:
        Group.objects.get_or_create(name=role)


def user_has_any_role(user, roles: tuple[str, ...]) -> bool:
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name__in=roles).exists()


def management_required(view):
    return user_passes_test(
        lambda user: user_has_any_role(user, MANAGEMENT_ROLES),
        login_url="identity:login",
    )(view)


def field_access_required(view):
    return user_passes_test(
        lambda user: user_has_any_role(user, FIELD_ROLES),
        login_url="identity:login",
    )(view)


def require_api_role(user, roles: tuple[str, ...]) -> None:
    if not user_has_any_role(user, roles):
        raise PermissionDenied("No tienes permiso para acceder a este recurso.")
