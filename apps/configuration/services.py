from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models import Q
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.identity.access import ROLE_OWNER, ensure_role_groups
from apps.tenants.models import Client

from .models import OrganizationCapability, OrganizationProfile


def provision_owner(
    organization: Client,
    *,
    username: str,
    email: str = "",
    password: str,
):
    with tenant_context(organization):
        ensure_role_groups()
        user = get_user_model().objects.create_user(
            username=username,
            email=email,
            password=password,
        )
        user.groups.add(Group.objects.get(name=ROLE_OWNER))
        return user


def active_profile_codes(organization: Client) -> set[str]:
    return set(
        OrganizationProfile.objects.filter(organization=organization, is_active=True).values_list(
            "profile__code",
            flat=True,
        )
    )


def enabled_capability_codes(organization: Client) -> set[str]:
    today = timezone.localdate()
    return set(
        OrganizationCapability.objects.filter(
            organization=organization,
            status__in=(
                OrganizationCapability.Status.TRIAL,
                OrganizationCapability.Status.ENABLED,
            ),
        )
        .filter(Q(expires_on__isnull=True) | Q(expires_on__gte=today))
        .values_list("capability__code", flat=True)
    )
