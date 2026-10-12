from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context, tenant_context

from apps.configuration.models import OrganizationCapability, OrganizationProfile
from apps.herd.models import Animal, Farm
from apps.identity.access import MANAGEMENT_ROLES
from apps.inventory.models import Input, StockLot
from apps.tenants.models import Domain

REQUIRED_CAPABILITIES = {
    "documents",
    "field_offline",
    "finance",
    "health",
    "herd",
    "inventory",
    "milk",
    "reproduction",
}


class Command(BaseCommand):
    help = "Validate that a tenant has the minimum data and access required for a pilot demo."

    def add_arguments(self, parser):
        parser.add_argument("--domain", required=True, help="Primary tenant domain to validate.")

    def handle(self, *args, **options):
        domain_name = options["domain"].strip().lower()
        failures: list[str] = []

        with schema_context(get_public_schema_name()):
            try:
                domain = Domain.objects.select_related("tenant").get(domain=domain_name)
            except Domain.DoesNotExist as exc:
                raise CommandError(f"No existe un tenant para el dominio {domain_name}.") from exc

            tenant = domain.tenant
            if tenant.schema_name == get_public_schema_name():
                raise CommandError("El dominio indicado pertenece a la plataforma, no a una finca.")

            self._check(
                failures,
                "Perfil operativo activo",
                OrganizationProfile.objects.filter(
                    organization=tenant,
                    is_active=True,
                ).exists(),
            )

            available_capabilities = {
                assignment.capability.code
                for assignment in OrganizationCapability.objects.filter(
                    organization=tenant,
                    capability__code__in=REQUIRED_CAPABILITIES,
                ).select_related("capability")
                if assignment.is_available
            }
            missing_capabilities = sorted(REQUIRED_CAPABILITIES - available_capabilities)
            self._check(
                failures,
                "Capacidades del MVP habilitadas",
                not missing_capabilities,
                f"faltan: {', '.join(missing_capabilities)}" if missing_capabilities else "",
            )

            service_current = not tenant.paid_until or tenant.paid_until >= timezone.localdate()
            self._check(
                failures,
                "Vigencia comercial",
                service_current,
                f"venció el {tenant.paid_until}" if not service_current else "",
            )

        with tenant_context(tenant):
            management_user_exists = (
                get_user_model()
                .objects.filter(is_active=True, groups__name__in=MANAGEMENT_ROLES)
                .distinct()
                .exists()
            )
            self._check(failures, "Usuario propietario o administrador", management_user_exists)
            self._check(failures, "Hacienda activa", Farm.objects.filter(is_active=True).exists())
            self._check(failures, "Animal activo", Animal.objects.filter(is_active=True).exists())
            self._check(failures, "Insumo activo", Input.objects.filter(is_active=True).exists())
            self._check(
                failures,
                "Stock disponible",
                StockLot.objects.filter(is_active=True, quantity_on_hand__gt=0).exists(),
            )

        if failures:
            raise CommandError(
                f"El tenant {domain_name} no está listo para el piloto: " + "; ".join(failures)
            )

        self.stdout.write(self.style.SUCCESS(f"Tenant listo para demo: {domain_name}"))

    def _check(
        self,
        failures: list[str],
        label: str,
        passed: bool,
        detail: str = "",
    ) -> None:
        if passed:
            self.stdout.write(self.style.SUCCESS(f"[OK] {label}"))
            return
        message = f"{label} ({detail})" if detail else label
        failures.append(message)
        self.stdout.write(self.style.ERROR(f"[FALTA] {message}"))
