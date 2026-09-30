from functools import wraps

from django.contrib.auth.decorators import login_required, user_passes_test
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

ROLE_PERMISSIONS = {
    ROLE_OWNER: {
        "audit.view_auditevent",
        "audit.export_audit",
        "parties.add_counterparty",
        "parties.change_counterparty",
        "parties.view_counterparty",
        "procurement.add_purchaseorder",
        "procurement.change_purchaseorder",
        "procurement.view_purchaseorder",
        "procurement.submit_purchaseorder",
        "procurement.approve_purchaseorder",
        "procurement.receive_purchaseorder",
        "procurement.manage_purchaseinvoice",
        "procurement.pay_purchaseinvoice",
        "procurement.return_purchase",
    },
    ROLE_MANAGER: {
        "audit.view_auditevent",
        "parties.add_counterparty",
        "parties.change_counterparty",
        "parties.view_counterparty",
        "procurement.add_purchaseorder",
        "procurement.change_purchaseorder",
        "procurement.view_purchaseorder",
        "procurement.submit_purchaseorder",
        "procurement.receive_purchaseorder",
        "procurement.manage_purchaseinvoice",
        "procurement.return_purchase",
    },
    ROLE_FIELD_WORKER: {"procurement.receive_purchaseorder"},
}


def ensure_role_groups():
    from django.contrib.auth.models import Group, Permission
    from django.db.models import Q

    for role in ROLE_LABELS:
        group, _ = Group.objects.get_or_create(name=role)
        query = Q()
        for permission_name in ROLE_PERMISSIONS.get(role, set()):
            app_label, codename = permission_name.split(".", 1)
            query |= Q(content_type__app_label=app_label, codename=codename)
        if query:
            group.permissions.add(*Permission.objects.filter(query))


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


def tenant_permission_required(permission_name: str):
    def decorator(view):
        @login_required(login_url="identity:login")
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.user.is_superuser or request.user.has_perm(permission_name):
                return view(request, *args, **kwargs)
            raise PermissionDenied("No tienes permiso para ejecutar esta accion.")

        return wrapped

    return decorator


def require_api_permission(user, permission_name: str) -> None:
    if not (user.is_superuser or user.has_perm(permission_name)):
        raise PermissionDenied("No tienes permiso para ejecutar esta accion.")


def accessible_farms_for_user(user):
    from apps.herd.models import Farm
    from apps.identity.models import FieldAssignment

    farms = Farm.objects.filter(is_active=True)
    if user_has_any_role(user, MANAGEMENT_ROLES):
        return farms

    assigned_farm_id = (
        FieldAssignment.objects.filter(user=user, is_active=True)
        .values_list("farm_id", flat=True)
        .first()
    )
    if assigned_farm_id:
        return farms.filter(id=assigned_farm_id)

    # A single-farm tenant remains zero-configuration for field workers.
    if farms.count() == 1:
        return farms
    return farms.none()


def require_api_role(user, roles: tuple[str, ...]) -> None:
    if not user_has_any_role(user, roles):
        raise PermissionDenied("No tienes permiso para acceder a este recurso.")
