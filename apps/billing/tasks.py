from celery import shared_task

from .models import MilkInvoice
from .services import request_sri_submission


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def submit_milk_invoice_to_sri(self, invoice_id: str):
    invoice = MilkInvoice.objects.get(id=invoice_id)
    request_sri_submission(invoice)
    return {"invoice_id": str(invoice.id), "status": invoice.status}
