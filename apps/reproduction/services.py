from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.herd.models import Animal, Farm

from .models import ReproductionEvent

GESTATION_DAYS = 283
PREGNANCY_CHECK_DAYS_AFTER_SERVICE = 45
DRY_OFF_DAYS_BEFORE_CALVING = 60


@transaction.atomic
def record_reproduction_event(
    *,
    farm: Farm,
    animal: Animal,
    event_type: str,
    occurred_on,
    source_event_id: UUID | None = None,
    payload: dict | None = None,
) -> ReproductionEvent:
    payload = payload or {}
    event = ReproductionEvent.objects.create(
        farm=farm,
        animal=animal,
        group=animal.current_group,
        event_type=event_type,
        occurred_on=occurred_on,
        service_type=payload.get("service_type", ""),
        sire_identifier=payload.get("sire_identifier", ""),
        pregnancy_positive=payload.get("pregnancy_positive"),
        calf_tag=payload.get("calf_tag", ""),
        calf_sex=payload.get("calf_sex", ""),
        payload=payload,
        source_event_id=source_event_id,
    )

    update_fields = ["updated_at"]

    if event_type == ReproductionEvent.EventType.SERVICE:
        animal.last_service_date = occurred_on
        animal.expected_calving_date = occurred_on + timedelta(days=GESTATION_DAYS)
        update_fields.extend(["last_service_date", "expected_calving_date"])

    if event_type == ReproductionEvent.EventType.PREGNANCY_CHECK:
        animal.confirmed_pregnant_at = occurred_on if payload.get("pregnancy_positive") else None
        if payload.get("pregnancy_positive"):
            animal.status = Animal.Status.PREGNANT
            update_fields.extend(["confirmed_pregnant_at", "status"])
        else:
            update_fields.append("confirmed_pregnant_at")

    if event_type == ReproductionEvent.EventType.CALVING:
        animal.status = Animal.Status.LACTATING
        animal.last_calving_date = occurred_on
        animal.lactation_number += 1
        animal.confirmed_pregnant_at = None
        animal.expected_calving_date = None
        update_fields.extend(
            [
                "status",
                "last_calving_date",
                "lactation_number",
                "confirmed_pregnant_at",
                "expected_calving_date",
            ]
        )
        _create_calf_if_present(
            farm=farm,
            dam=animal,
            payload=payload,
            source_event_id=source_event_id,
        )

    if event_type == ReproductionEvent.EventType.DRY_OFF:
        animal.status = Animal.Status.DRY
        animal.dry_off_date = occurred_on
        update_fields.extend(["status", "dry_off_date"])

    animal.save(update_fields=list(dict.fromkeys(update_fields)))
    return event


def _create_calf_if_present(
    *,
    farm: Farm,
    dam: Animal,
    payload: dict,
    source_event_id: UUID | None,
) -> None:
    calf_tag = payload.get("calf_tag")
    calf_id = payload.get("calf_id")
    if not calf_tag:
        return

    defaults = {
        "farm": farm,
        "tag": calf_tag,
        "sex": payload.get("calf_sex") or Animal.Sex.FEMALE,
        "status": Animal.Status.CALF,
        "birth_date": _date_or_today(payload.get("birth_date")),
        "dam": dam,
        "source_device_id": dam.source_device_id,
    }
    if calf_id:
        Animal.objects.get_or_create(id=calf_id, defaults=defaults)
    else:
        Animal.objects.get_or_create(farm=farm, tag=calf_tag, defaults=defaults)


def _date_or_today(value):
    if not value:
        return timezone.localdate()
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value
    return parse_date(str(value)) or timezone.localdate()


def daily_reproduction_attention(today=None):
    today = today or timezone.localdate()
    dry_off_target = today + timedelta(days=DRY_OFF_DAYS_BEFORE_CALVING)
    pregnancy_check_cutoff = today - timedelta(days=PREGNANCY_CHECK_DAYS_AFTER_SERVICE)

    dry_off = Animal.objects.filter(
        expected_calving_date__lte=dry_off_target,
        dry_off_date__isnull=True,
        status__in=[Animal.Status.PREGNANT, Animal.Status.LACTATING],
    ).order_by("expected_calving_date", "tag")

    pregnancy_checks = Animal.objects.filter(
        last_service_date__lte=pregnancy_check_cutoff,
        confirmed_pregnant_at__isnull=True,
        status__in=[Animal.Status.HEIFER, Animal.Status.LACTATING],
    ).order_by("last_service_date", "tag")

    return {
        "dry_off": dry_off,
        "pregnancy_checks": pregnancy_checks,
    }
