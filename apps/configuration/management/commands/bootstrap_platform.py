from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import get_public_schema_name, schema_context

from apps.tenants.models import Client, Domain


class Command(BaseCommand):
    help = "Create the public platform tenant, domain and initial superuser."

    def add_arguments(self, parser):
        parser.add_argument("--domain", default="127.0.0.1")
        parser.add_argument("--username", default="superadmin")
        parser.add_argument("--email", default="")
        parser.add_argument("--password")

    def handle(self, *args, **options):
        if not options["password"]:
            raise CommandError("--password is required.")

        schema_name = get_public_schema_name()
        with schema_context(schema_name):
            platform, _ = Client.objects.get_or_create(
                schema_name=schema_name,
                defaults={
                    "name": "KORE Agro Plataforma",
                    "legal_name": "BINNSO",
                    "on_trial": False,
                },
            )
            primary_domain, _ = Domain.objects.update_or_create(
                domain=options["domain"],
                defaults={"tenant": platform, "is_primary": True},
            )
            Domain.objects.filter(tenant=platform).exclude(pk=primary_domain.pk).update(
                is_primary=False
            )
            user_model = get_user_model()
            user, _ = user_model.objects.get_or_create(
                username=options["username"],
                defaults={"email": options["email"]},
            )
            user.email = options["email"]
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.set_password(options["password"])
            user.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Panel listo: domain={options['domain']} username={options['username']}"
            )
        )
