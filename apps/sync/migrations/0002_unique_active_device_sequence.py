from django.db import migrations, models
from django.db.models import Case, IntegerField, Value, When


def resolve_existing_sequence_collisions(apps, schema_editor):
    IncomingEvent = apps.get_model("sync", "IncomingEvent")
    collisions = (
        IncomingEvent.objects.exclude(status="conflict")
        .values("device_id", "client_sequence")
        .annotate(total=models.Count("event_id"))
        .filter(total__gt=1)
    )

    status_priority = Case(
        When(status="processed", then=Value(0)),
        When(status="processing", then=Value(1)),
        When(status="received", then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )
    for collision in collisions.iterator():
        event_ids = list(
            IncomingEvent.objects.filter(
                device_id=collision["device_id"],
                client_sequence=collision["client_sequence"],
            )
            .exclude(status="conflict")
            .order_by(status_priority, "created_at", "event_id")
            .values_list("event_id", flat=True)
        )
        IncomingEvent.objects.filter(event_id__in=event_ids[1:]).update(
            status="conflict",
            error_code="client_sequence_reused",
            error_message="Migrated duplicate device sequence; manual review required.",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("sync", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(resolve_existing_sequence_collisions, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="incomingevent",
            constraint=models.UniqueConstraint(
                fields=("device_id", "client_sequence"),
                condition=~models.Q(status="conflict"),
                name="unique_active_device_sequence",
            ),
        ),
    ]
