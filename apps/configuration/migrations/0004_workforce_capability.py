from django.db import migrations


def add_workforce_capability(apps, schema_editor):
    Profile = apps.get_model("configuration", "ProfileDefinition")
    Capability = apps.get_model("configuration", "CapabilityDefinition")
    capability, _ = Capability.objects.update_or_create(
        code="workforce",
        defaults={
            "name": "Personal y tareas",
            "category": "operations",
            "description": "Asignacion de trabajo, jornadas y costo de mano de obra",
            "sort_order": 80,
            "is_active": True,
        },
    )
    capability.compatible_profiles.set(Profile.objects.filter(is_active=True))


class Migration(migrations.Migration):
    dependencies = [("configuration", "0003_grazing_dependency")]

    operations = [migrations.RunPython(add_workforce_capability, migrations.RunPython.noop)]
