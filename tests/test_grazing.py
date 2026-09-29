from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context, tenant_context

from apps.configuration.models import OrganizationCapability
from apps.grazing.models import GrazingPeriod, Paddock
from apps.grazing.services import (
    finish_grazing_period,
    get_paddock_summaries,
    start_grazing_period,
)
from apps.herd.models import HerdGroup
from apps.sync.services import ActionEventMessage, process_action_event
from tests.factories import authenticated_manager_client, create_tenant, seed_farm


@pytest.mark.django_db(transaction=True)
def test_rotation_prevents_double_paddock_or_group_occupancy():
    tenant = create_tenant("grazingrules")
    with tenant_context(tenant):
        farm, group, _, _, _ = seed_farm()
        second_group = HerdGroup.objects.create(farm=farm, name="Reemplazos")
        first_paddock = Paddock.objects.create(
            farm=farm,
            name="Norte",
            code="NORTE",
            area_hectares=Decimal("3.50"),
        )
        second_paddock = Paddock.objects.create(
            farm=farm,
            name="Sur",
            code="SUR",
            area_hectares=Decimal("2.25"),
        )

        start_grazing_period(
            farm=farm,
            paddock=first_paddock,
            group=group,
            head_count=12,
        )

        with pytest.raises(ValidationError, match="ocupado"):
            start_grazing_period(
                farm=farm,
                paddock=first_paddock,
                group=second_group,
                head_count=8,
            )
        with pytest.raises(ValidationError, match="otro potrero"):
            start_grazing_period(
                farm=farm,
                paddock=second_paddock,
                group=group,
                head_count=12,
            )


@pytest.mark.django_db(transaction=True)
def test_finished_rotation_updates_rest_and_availability_summary():
    tenant = create_tenant("grazingrest")
    with tenant_context(tenant):
        farm, group, _, _, _ = seed_farm()
        paddock = Paddock.objects.create(
            farm=farm,
            name="Reserva",
            code="RES",
            area_hectares=Decimal("4.00"),
            rest_target_days=21,
        )
        today = timezone.localdate()
        period = start_grazing_period(
            farm=farm,
            paddock=paddock,
            group=group,
            started_on=today - timedelta(days=4),
            head_count=10,
            entry_biomass_kg_ha=Decimal("2800"),
        )
        period = finish_grazing_period(
            period,
            ended_on=today - timedelta(days=1),
            exit_biomass_kg_ha=Decimal("1450"),
        )
        summary = get_paddock_summaries(farm=farm)[0]

        assert period.occupied_days == 4
        assert summary.status == "resting"
        assert summary.rest_days == 1
        assert summary.rest_days_remaining == 20
        with pytest.raises(ValidationError, match="adicionales de descanso"):
            start_grazing_period(
                farm=farm,
                paddock=paddock,
                group=group,
                head_count=10,
            )


@pytest.mark.django_db(transaction=True)
def test_manager_can_create_paddock_start_and_finish_rotation():
    tenant = create_tenant("grazingweb")
    with tenant_context(tenant):
        farm, group, _, _, _ = seed_farm()
    client = authenticated_manager_client(tenant)

    create_response = client.post(
        "/pastoreo/potreros/crear/",
        {
            "farm": str(farm.id),
            "name": "Potrero Uno",
            "code": "P-01",
            "area_hectares": "3.75",
            "forage_type": "Kikuyo",
            "rest_target_days": "24",
            "capacity_animals": "30",
            "notes": "",
        },
    )
    assert create_response.status_code == 200
    assert "Potrero Potrero Uno creado" in create_response.content.decode()

    with tenant_context(tenant):
        paddock = Paddock.objects.get(code="P-01")

    start_response = client.post(
        "/pastoreo/rotaciones/iniciar/",
        {
            "farm": str(farm.id),
            "paddock": str(paddock.id),
            "group": str(group.id),
            "started_on": timezone.localdate().isoformat(),
            "planned_end_on": "",
            "head_count": "18",
            "entry_biomass_kg_ha": "2650",
            "notes": "Entrada de prueba",
        },
    )
    assert start_response.status_code == 200
    assert "ingreso a Potrero Uno" in start_response.content.decode()

    with tenant_context(tenant):
        period = GrazingPeriod.objects.get(paddock=paddock, ended_on__isnull=True)

    finish_response = client.post(
        f"/pastoreo/rotaciones/{period.id}/cerrar/",
        {
            "ended_on": timezone.localdate().isoformat(),
            "exit_biomass_kg_ha": "1350",
            "notes": "Salida de prueba",
        },
    )
    assert finish_response.status_code == 200
    assert "Salida registrada" in finish_response.content.decode()
    with tenant_context(tenant):
        period.refresh_from_db()
        assert period.ended_on is not None
        assert period.exit_biomass_kg_ha == Decimal("1350")


@pytest.mark.django_db(transaction=True)
def test_grazing_route_requires_the_capability():
    tenant = create_tenant("grazingaccess")
    client = authenticated_manager_client(tenant)
    with schema_context(get_public_schema_name()):
        assignment = OrganizationCapability.objects.get(
            organization=tenant,
            capability__code="grazing",
        )
        assignment.status = OrganizationCapability.Status.SUSPENDED
        assignment.save(update_fields=["status"])

    response = client.get("/pastoreo/")
    home_response = client.get("/")

    assert response.status_code == 403
    assert "Potreros y rotacion" not in home_response.content.decode()


@pytest.mark.django_db(transaction=True)
def test_offline_rotation_event_is_idempotent():
    from uuid import uuid4

    tenant = create_tenant("grazingsync")
    with tenant_context(tenant):
        farm, group, _, _, _ = seed_farm()
        paddock = Paddock.objects.create(
            farm=farm,
            name="Campo Alto",
            code="ALTO",
            area_hectares=Decimal("5.20"),
        )
        message = ActionEventMessage(
            event_id=uuid4(),
            device_id=uuid4(),
            actor_id=None,
            tenant_id=None,
            client_sequence=1,
            schema_version=1,
            event_type="grazing.rotation_started",
            occurred_at=timezone.now(),
            payload={
                "farm_id": str(farm.id),
                "paddock_id": str(paddock.id),
                "group_id": str(group.id),
                "started_on": timezone.localdate().isoformat(),
                "head_count": "14",
                "entry_biomass_kg_ha": "2750",
            },
        )

        first = process_action_event(message)
        second = process_action_event(message)

        assert first.status == "acked"
        assert second.status == "acked"
        assert second.detail == "already_processed"
        period = GrazingPeriod.objects.get()
        assert period.head_count == 14
        assert period.source_event_id == message.event_id
