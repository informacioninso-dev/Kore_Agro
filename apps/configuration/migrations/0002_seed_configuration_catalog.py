from django.db import migrations


PROFILES = [
    ("livestock", "Ganaderia", "Produccion ganadera, lechera y manejo del hato", 10),
    ("coffee", "Cafe", "Produccion, beneficio y trazabilidad de cafe", 20),
    ("cacao", "Cacao", "Produccion, fermentacion, secado y calidad de cacao", 30),
    ("collection_center", "Centro de Acopio", "Recepcion y liquidacion de producto", 40),
    ("processing", "Procesamiento", "Transformaciones, rendimientos y mermas", 50),
    ("commerce", "Comercializacion", "Ventas, pedidos, despacho y cartera", 60),
]

CAPABILITIES = [
    ("herd", "Hato", "production", ["livestock"], 10),
    ("milk", "Produccion de leche", "production", ["livestock"], 20),
    ("reproduction", "Reproduccion", "production", ["livestock"], 30),
    ("health", "Sanidad animal", "production", ["livestock"], 40),
    ("growth", "Pesajes y crecimiento", "production", ["livestock"], 50),
    ("grazing", "Pastoreo y potreros", "production", ["livestock"], 60),
    (
        "counterparties",
        "Productores y contrapartes",
        "foundation",
        ["coffee", "cacao", "collection_center", "commerce"],
        10,
    ),
    (
        "reception",
        "Recepcion de producto",
        "operations",
        ["coffee", "cacao", "collection_center"],
        10,
    ),
    (
        "weighing",
        "Pesaje operativo",
        "operations",
        ["livestock", "coffee", "cacao", "collection_center"],
        20,
    ),
    (
        "quality",
        "Control de calidad",
        "operations",
        ["coffee", "cacao", "collection_center"],
        30,
    ),
    (
        "lots",
        "Lotes y consolidacion",
        "operations",
        ["coffee", "cacao", "collection_center", "processing", "commerce"],
        40,
    ),
    ("settlements", "Liquidaciones", "finance", ["collection_center"], 10),
    (
        "inventory",
        "Inventario y bodega",
        "inventory",
        [profile[0] for profile in PROFILES],
        10,
    ),
    (
        "traceability",
        "Trazabilidad",
        "operations",
        [profile[0] for profile in PROFILES],
        50,
    ),
    (
        "dispatch",
        "Despacho",
        "operations",
        ["collection_center", "processing", "commerce"],
        60,
    ),
    (
        "processing",
        "Ordenes de procesamiento",
        "operations",
        ["coffee", "cacao", "processing"],
        70,
    ),
    (
        "commerce",
        "Ventas y comercializacion",
        "finance",
        [profile[0] for profile in PROFILES],
        20,
    ),
    (
        "finance",
        "Costos y rentabilidad",
        "finance",
        [profile[0] for profile in PROFILES],
        30,
    ),
    (
        "documents",
        "Documentos y cumplimiento",
        "compliance",
        [profile[0] for profile in PROFILES],
        10,
    ),
    (
        "field_offline",
        "Operacion de campo offline",
        "foundation",
        [profile[0] for profile in PROFILES],
        20,
    ),
]

DEPENDENCIES = {
    "reception": ["counterparties", "weighing"],
    "quality": ["reception"],
    "lots": ["reception"],
    "settlements": ["reception", "quality"],
    "traceability": ["lots"],
    "dispatch": ["inventory", "lots"],
    "processing": ["inventory", "lots"],
}


def seed_catalog(apps, schema_editor):
    Profile = apps.get_model("configuration", "ProfileDefinition")
    Capability = apps.get_model("configuration", "CapabilityDefinition")
    OrganizationProfile = apps.get_model("configuration", "OrganizationProfile")
    OrganizationCapability = apps.get_model("configuration", "OrganizationCapability")
    Client = apps.get_model("tenants", "Client")

    profiles = {}
    for code, name, description, sort_order in PROFILES:
        profiles[code], _ = Profile.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "description": description,
                "sort_order": sort_order,
                "is_active": True,
            },
        )

    capabilities = {}
    for code, name, category, profile_codes, sort_order in CAPABILITIES:
        capability, _ = Capability.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "category": category,
                "sort_order": sort_order,
                "is_active": True,
            },
        )
        capability.compatible_profiles.set([profiles[item] for item in profile_codes])
        capabilities[code] = capability

    for code, dependency_codes in DEPENDENCIES.items():
        capabilities[code].dependencies.set(
            [capabilities[dependency] for dependency in dependency_codes]
        )

    livestock_capabilities = [
        "herd",
        "milk",
        "reproduction",
        "health",
        "growth",
        "inventory",
        "finance",
        "documents",
        "field_offline",
    ]
    for organization in Client.objects.exclude(schema_name="public"):
        OrganizationProfile.objects.get_or_create(
            organization=organization,
            profile=profiles["livestock"],
            defaults={"is_active": True},
        )
        status = "trial" if organization.on_trial else "enabled"
        for code in livestock_capabilities:
            OrganizationCapability.objects.get_or_create(
                organization=organization,
                capability=capabilities[code],
                defaults={"status": status},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("configuration", "0001_initial"),
        ("tenants", "0001_initial"),
    ]

    operations = [migrations.RunPython(seed_catalog, migrations.RunPython.noop)]
