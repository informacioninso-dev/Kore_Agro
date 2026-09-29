from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.growth.models import WeightRecord
from apps.growth.services import get_animal_growth, record_weight, summarize_groups
from apps.herd.models import Animal, Farm
from apps.sync.services import ActionEventMessage, process_action_event
from tests.factories import authenticated_manager_client, create_tenant, seed_farm


@pytest.mark.django_db(transaction=True)
def test_growth_metric_calculates_daily_gain_and_group_summary():
    tenant = create_tenant("growthmetric")
    with tenant_context(tenant):
        farm, group, animal, _, _ = seed_farm()
        today = timezone.localdate()
        record_weight(
            farm=farm,
            animal=animal,
            weight_kg=Decimal("400"),
            weighed_on=today - timedelta(days=20),
        )
        record_weight(
            farm=farm,
            animal=animal,
            weight_kg=Decimal("420"),
            weighed_on=today,
        )

        metric = get_animal_growth(animal)
        summaries = summarize_groups([metric])

        assert metric.gain_kg == Decimal("20.00")
        assert metric.days_between == 20
        assert metric.daily_gain == Decimal("1.000")
        assert metric.projected_days_to(Decimal("500")) == 80
        assert summaries[0].group == group
        assert summaries[0].average_daily_gain == Decimal("1.000")


@pytest.mark.django_db(transaction=True)
def test_weight_record_rejects_animal_from_another_farm():
    tenant = create_tenant("growthfarm")
    with tenant_context(tenant):
        farm, _, _, _, _ = seed_farm()
        other_farm = Farm.objects.create(name="Hacienda ajena", code="AJENA")
        other_animal = Animal.objects.create(farm=other_farm, tag="OTRO-1")

        with pytest.raises(ValidationError, match="no pertenece"):
            record_weight(
                farm=farm,
                animal=other_animal,
                weight_kg=Decimal("250"),
            )


@pytest.mark.django_db(transaction=True)
def test_offline_weight_event_is_idempotent():
    tenant = create_tenant("growthsync")
    with tenant_context(tenant):
        farm, _, animal, _, _ = seed_farm()
        message = ActionEventMessage(
            event_id=uuid4(),
            device_id=uuid4(),
            actor_id=None,
            tenant_id=None,
            client_sequence=1,
            schema_version=1,
            event_type="growth.weight_recorded",
            occurred_at=timezone.now(),
            payload={
                "farm_id": str(farm.id),
                "animal_id": str(animal.id),
                "weight_kg": "415.50",
                "body_condition_score": "3.5",
                "weighed_on": timezone.localdate().isoformat(),
            },
        )

        first = process_action_event(message)
        second = process_action_event(message)

        assert first.status == "acked"
        assert second.status == "acked"
        assert second.detail == "already_processed"
        assert WeightRecord.objects.get().weight_kg == Decimal("415.50")


@pytest.mark.django_db(transaction=True)
def test_manager_can_record_weight_and_open_animal_timeline():
    tenant = create_tenant("growthweb")
    with tenant_context(tenant):
        farm, _, animal, _, _ = seed_farm()
    client = authenticated_manager_client(tenant)

    response = client.post(
        "/crecimiento/pesaje/",
        {
            "farm": str(farm.id),
            "animal": str(animal.id),
            "weighed_on": timezone.localdate().isoformat(),
            "weight_kg": "390.25",
            "body_condition_score": "3.0",
            "scale_identifier": "Bascula corral",
            "notes": "Control mensual",
        },
    )

    assert response.status_code == 200
    assert "Pesaje guardado" in response.content.decode()
    with tenant_context(tenant):
        assert WeightRecord.objects.filter(animal=animal).count() == 1

    growth_response = client.get(f"/crecimiento/?farm={farm.id}")
    timeline_response = client.get(f"/animales/{animal.id}/historial/")

    assert growth_response.status_code == 200
    assert growth_response.context["growth_rows"][0]["metric"].latest.weight_kg == Decimal(
        "390.25"
    )
    assert timeline_response.status_code == 200
    timeline_html = timeline_response.content.decode()
    assert f"Arete {animal.tag}" in timeline_html
    assert "Pesaje" in timeline_html
