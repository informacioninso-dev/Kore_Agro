from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.herd.models import Animal, Farm, HerdGroup
from apps.inventory.models import Input, StockLot
from apps.tenants.models import Client, Domain


class Command(BaseCommand):
    help = "Create a local demo tenant with MVP seed data."

    def add_arguments(self, parser):
        parser.add_argument("--schema", default="demo")
        parser.add_argument("--domain", default="localhost")

    def handle(self, *args, **options):
        schema_name = options["schema"]
        domain_name = options["domain"]

        tenant, _ = Client.objects.get_or_create(
            schema_name=schema_name,
            defaults={
                "name": "Hacienda Demo KORE",
                "legal_name": "Hacienda Demo KORE S.A.",
                "ruc": "1799999999001",
                "province": "Pichincha",
                "city": "Quito",
                "paid_until": timezone.localdate() + timedelta(days=30),
                "on_trial": True,
            },
        )
        Domain.objects.get_or_create(
            domain=domain_name,
            defaults={"tenant": tenant, "is_primary": True},
        )

        with tenant_context(tenant):
            farm, _ = Farm.objects.get_or_create(
                code="HDK",
                defaults={
                    "name": "Hacienda Demo KORE",
                    "province": "Pichincha",
                    "canton": "Quito",
                    "default_milk_price": Decimal("0.45"),
                },
            )
            lote, _ = HerdGroup.objects.get_or_create(
                farm=farm,
                name="Lote Produccion",
                defaults={"group_type": HerdGroup.GroupType.LOT},
            )

            animals = [
                ("101", "Mora", Animal.Status.LACTATING, 35),
                ("118", "Luna", Animal.Status.LACTATING, 72),
                ("125", "Nube", Animal.Status.PREGNANT, 190),
            ]
            for tag, name, status, days_since_calving in animals:
                Animal.objects.get_or_create(
                    farm=farm,
                    tag=tag,
                    defaults={
                        "name": name,
                        "current_group": lote,
                        "status": status,
                        "sex": Animal.Sex.FEMALE,
                        "last_calving_date": timezone.localdate()
                        - timedelta(days=days_since_calving),
                        "last_service_date": timezone.localdate() - timedelta(days=50),
                        "expected_calving_date": timezone.localdate() + timedelta(days=70),
                        "bos_taurus_pct": Decimal("62.50"),
                        "bos_indicus_pct": Decimal("37.50"),
                    },
                )

            balanceado, _ = Input.objects.get_or_create(
                sku="BAL-40KG",
                defaults={
                    "name": "Balanceado 40kg",
                    "category": Input.Category.FEED,
                    "unit": Input.Unit.SACK,
                    "default_unit_cost": Decimal("18.50"),
                },
            )
            aftosa, _ = Input.objects.get_or_create(
                sku="AFT-DOSIS",
                defaults={
                    "name": "Vacuna aftosa",
                    "category": Input.Category.VACCINE,
                    "unit": Input.Unit.DOSE,
                    "default_unit_cost": Decimal("1.25"),
                    "milk_withdrawal_hours": 0,
                },
            )
            antibiotico, _ = Input.objects.get_or_create(
                sku="ATB-ML",
                defaults={
                    "name": "Antibiotico mastitis",
                    "category": Input.Category.MEDICINE,
                    "unit": Input.Unit.ML,
                    "default_unit_cost": Decimal("0.18"),
                    "milk_withdrawal_hours": 72,
                },
            )

            for input_, qty, cost in [
                (balanceado, Decimal("80"), Decimal("18.50")),
                (aftosa, Decimal("150"), Decimal("1.25")),
                (antibiotico, Decimal("1000"), Decimal("0.18")),
            ]:
                StockLot.objects.get_or_create(
                    farm=farm,
                    input=input_,
                    lot_code="DEMO",
                    defaults={
                        "quantity_on_hand": qty,
                        "unit_cost": cost,
                    },
                )

        self.stdout.write(
            self.style.SUCCESS(f"Tenant listo: schema={schema_name}, domain={domain_name}")
        )
