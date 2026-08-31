from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_tenants.utils import tenant_context

from apps.identity.access import ROLE_LABELS, ensure_role_groups
from apps.tenants.models import Client


class Command(BaseCommand):
    help = "Create or update a role-assigned user inside a tenant schema."

    def add_arguments(self, parser):
        parser.add_argument("--schema", required=True, help="Tenant schema name.")
        parser.add_argument("--username", required=True)
        parser.add_argument("--password", required=True)
        parser.add_argument("--role", choices=ROLE_LABELS, required=True)
        parser.add_argument("--email", default="")

    def handle(self, *args, **options):
        try:
            tenant = Client.objects.get(schema_name=options["schema"])
        except Client.DoesNotExist as exc:
            raise CommandError(f"Tenant schema not found: {options['schema']}") from exc

        with tenant_context(tenant), transaction.atomic():
            ensure_role_groups()
            user_model = get_user_model()
            user, created = user_model.objects.get_or_create(username=options["username"])
            user.email = options["email"]
            user.set_password(options["password"])
            user.is_active = True
            user.save()
            user.groups.clear()
            user.groups.add(Group.objects.get(name=options["role"]))

        status = "created" if created else "updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"User {status}: {options['username']} ({ROLE_LABELS[options['role']]})"
            )
        )
