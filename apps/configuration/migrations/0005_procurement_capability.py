from django.db import migrations


def add_procurement_capability(apps, schema_editor):
    Profile = apps.get_model("configuration", "ProfileDefinition")
    Capability = apps.get_model("configuration", "CapabilityDefinition")
    counterparties = Capability.objects.get(code="counterparties")
    inventory = Capability.objects.get(code="inventory")
    profiles = Profile.objects.filter(is_active=True)
    counterparties.compatible_profiles.set(profiles)

    procurement, _ = Capability.objects.update_or_create(
        code="procurement",
        defaults={
            "name": "Proveedores y compras",
            "category": "inventory",
            "description": "Ordenes, recepciones e ingreso trazable a inventario",
            "sort_order": 20,
            "is_active": True,
        },
    )
    procurement.compatible_profiles.set(profiles)
    procurement.dependencies.set([counterparties, inventory])


class Migration(migrations.Migration):
    dependencies = [("configuration", "0004_workforce_capability")]

    operations = [migrations.RunPython(add_procurement_capability, migrations.RunPython.noop)]
