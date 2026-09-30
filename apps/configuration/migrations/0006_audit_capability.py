from django.db import migrations


def add_audit_capability(apps, schema_editor):
    Profile = apps.get_model("configuration", "ProfileDefinition")
    Capability = apps.get_model("configuration", "CapabilityDefinition")
    capability, _ = Capability.objects.update_or_create(
        code="audit",
        defaults={
            "name": "Auditoria transversal",
            "category": "compliance",
            "description": "Historial de cambios, actores y origen de cada operacion",
            "sort_order": 20,
            "is_active": True,
        },
    )
    capability.compatible_profiles.set(Profile.objects.filter(is_active=True))


class Migration(migrations.Migration):
    dependencies = [("configuration", "0005_procurement_capability")]

    operations = [migrations.RunPython(add_audit_capability, migrations.RunPython.noop)]
