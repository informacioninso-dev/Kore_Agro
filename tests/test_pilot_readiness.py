from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context, tenant_context

from apps.tenants.models import Domain
from tests.factories import authenticated_manager_client, create_tenant, seed_farm


@pytest.mark.django_db(transaction=True)
def test_pilot_readiness_reports_missing_operational_data():
    tenant = create_tenant("pilotmissing")
    domain = Domain.objects.get(tenant=tenant).domain

    with pytest.raises(CommandError, match="no está listo para el piloto"):
        call_command("check_pilot_readiness", domain=domain, stdout=StringIO())


@pytest.mark.django_db(transaction=True)
def test_pilot_readiness_accepts_a_seeded_tenant_with_manager():
    tenant = create_tenant("pilotready")
    domain = Domain.objects.get(tenant=tenant).domain
    authenticated_manager_client(tenant)
    with tenant_context(tenant):
        seed_farm()

    output = StringIO()
    call_command("check_pilot_readiness", domain=domain, stdout=output)

    assert "[OK] Usuario propietario o administrador" in output.getvalue()
    assert f"Tenant listo para demo: {domain}" in output.getvalue()


@pytest.mark.django_db(transaction=True)
def test_demo_bootstrap_renews_an_existing_trial_without_replacing_data():
    with schema_context(get_public_schema_name()):
        tenant = create_tenant("demorenew")
        domain = Domain.objects.get(tenant=tenant).domain
        tenant.paid_until = timezone.localdate() - timedelta(days=1)
        tenant.save(update_fields=["paid_until"])

        call_command(
            "bootstrap_demo_tenant",
            schema=tenant.schema_name,
            domain=domain,
            stdout=StringIO(),
        )

        tenant.refresh_from_db()
        assert tenant.on_trial
        assert tenant.paid_until == timezone.localdate() + timedelta(days=30)
