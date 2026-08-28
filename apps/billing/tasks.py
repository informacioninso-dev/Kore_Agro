from celery import shared_task

from .models import MilkInvoice


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def submit_milk_invoice_to_sri(self, invoice_id: str):
    invoice = MilkInvoice.objects.get(id=invoice_id)
    invoice.sri_response = {
        "status": "pending_adapter",
        "detail": "SRI adapter will sign XML and submit in MVP week 7.",
    }
    invoice.save(update_fields=["sri_response", "updated_at"])
    return {"invoice_id": str(invoice.id), "status": invoice.status}
