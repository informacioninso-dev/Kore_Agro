from django.db import migrations


def add_grazing_dependency(apps, schema_editor):
    Capability = apps.get_model("configuration", "CapabilityDefinition")
    try:
        grazing = Capability.objects.get(code="grazing")
        herd = Capability.objects.get(code="herd")
    except Capability.DoesNotExist:
        return
    grazing.dependencies.add(herd)


class Migration(migrations.Migration):
    dependencies = [("configuration", "0002_seed_configuration_catalog")]

    operations = [migrations.RunPython(add_grazing_dependency, migrations.RunPython.noop)]
