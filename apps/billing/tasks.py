from celery import shared_task
from django_tenants.utils import get_public_schema_name, schema_context, tenant_context

from apps.tenants.models import Client

from .models import MilkInvoice
from .services import request_sri_submission


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def submit_milk_invoice_to_sri(self, schema_name: str, invoice_id: str):
    with schema_context(get_public_schema_name()):
        tenant = Client.objects.get(schema_name=schema_name)

    with tenant_context(tenant):
        invoice = MilkInvoice.objects.get(id=invoice_id)
        request_sri_submission(invoice)
        return {"invoice_id": str(invoice.id), "status": invoice.status}
