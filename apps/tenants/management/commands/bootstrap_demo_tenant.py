from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.configuration.models import (
    CapabilityDefinition,
    OrganizationCapability,
    OrganizationProfile,
    ProfileDefinition,
)
from apps.grazing.models import GrazingPeriod, Paddock
from apps.herd.models import Animal, Farm, HerdGroup
from apps.identity.access import ensure_role_groups
from apps.inventory.models import Input, StockLot
from apps.parties.models import Counterparty
from apps.procurement.models import PurchaseOrder, PurchaseOrderLine
from apps.tenants.models import Client, Domain
from apps.workforce.models import Worker, WorkTask


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
        livestock = ProfileDefinition.objects.get(code="livestock")
        OrganizationProfile.objects.update_or_create(
            organization=tenant,
            profile=livestock,
            defaults={"is_active": True},
        )
        capability_status = (
            OrganizationCapability.Status.TRIAL
            if tenant.on_trial
            else OrganizationCapability.Status.ENABLED
        )
        implemented_codes = [
            "herd",
            "milk",
            "reproduction",
            "health",
            "growth",
            "grazing",
            "workforce",
            "audit",
            "counterparties",
            "inventory",
            "procurement",
            "finance",
            "documents",
            "field_offline",
        ]
        for capability in CapabilityDefinition.objects.filter(code__in=implemented_codes):
            OrganizationCapability.objects.update_or_create(
                organization=tenant,
                capability=capability,
                defaults={"status": capability_status},
            )

        with tenant_context(tenant):
            ensure_role_groups()
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

            supplier, _ = Counterparty.objects.get_or_create(
                identification_number="1790012345001",
                defaults={
                    "legal_name": "Agroinsumos Sierra S.A.",
                    "trade_name": "AgroSierra",
                    "identification_type": Counterparty.IdentificationType.RUC,
                    "is_supplier": True,
                    "email": "ventas@agrosierra.example",
                    "phone": "022345678",
                    "province": "Pichincha",
                    "city": "Quito",
                    "payment_terms_days": 30,
                },
            )
            purchase_order, _ = PurchaseOrder.objects.get_or_create(
                number="OC-DEMO-001",
                defaults={
                    "farm": farm,
                    "supplier": supplier,
                    "ordered_on": timezone.localdate(),
                    "expected_on": timezone.localdate() + timedelta(days=3),
                    "status": PurchaseOrder.Status.ORDERED,
                    "notes": "Reposicion mensual de alimento",
                },
            )
            PurchaseOrderLine.objects.get_or_create(
                purchase_order=purchase_order,
                input=balanceado,
                defaults={
                    "quantity_ordered": Decimal("40"),
                    "unit_cost": Decimal("18.25"),
                    "tax_rate": Decimal("0"),
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

            north_paddock, _ = Paddock.objects.get_or_create(
                farm=farm,
                code="P-NORTE",
                defaults={
                    "name": "Potrero Norte",
                    "area_hectares": Decimal("3.50"),
                    "forage_type": "Ryegrass y trebol",
                    "rest_target_days": 28,
                    "capacity_animals": 35,
                },
            )
            Paddock.objects.get_or_create(
                farm=farm,
                code="P-SUR",
                defaults={
                    "name": "Potrero Sur",
                    "area_hectares": Decimal("2.80"),
                    "forage_type": "Kikuyo",
                    "rest_target_days": 24,
                    "capacity_animals": 28,
                },
            )
            admin_user = get_user_model().objects.filter(username="admin").first()
            worker, _ = Worker.objects.update_or_create(
                farm=farm,
                code="ADM-01",
                defaults={
                    "full_name": "Administrador Demo",
                    "position": Worker.Position.FOREMAN,
                    "hourly_rate": Decimal("4.50"),
                    "user": admin_user,
                },
            )
            WorkTask.objects.get_or_create(
                farm=farm,
                title="Revisar bebederos del Potrero Sur",
                scheduled_for=timezone.localdate(),
                defaults={
                    "category": WorkTask.Category.MAINTENANCE,
                    "priority": WorkTask.Priority.HIGH,
                    "assigned_to": worker,
                    "paddock": Paddock.objects.get(farm=farm, code="P-SUR"),
                    "estimated_hours": Decimal("1.50"),
                    "instructions": "Verificar caudal, limpieza y posibles fugas.",
                },
            )
            GrazingPeriod.objects.get_or_create(
                group=lote,
                ended_on__isnull=True,
                defaults={
                    "farm": farm,
                    "paddock": north_paddock,
                    "started_on": timezone.localdate() - timedelta(days=3),
                    "planned_end_on": timezone.localdate() + timedelta(days=2),
                    "head_count": 3,
                    "entry_biomass_kg_ha": Decimal("2850"),
                    "notes": "Rotacion demostrativa",
                },
            )

        self.stdout.write(
            self.style.SUCCESS(f"Tenant listo: schema={schema_name}, domain={domain_name}")
        )
