from celery import shared_task
from django_tenants.utils import get_public_schema_name, tenant_context

from apps.herd.models import Farm
from apps.tenants.models import Client

from .services import close_operating_period

AUTOMATED_CLOSE_NOTE = "Cierre operativo automatico."


def _close_farms(*, start_date=None, end_date=None, notes: str) -> list[dict]:
    results = []
    for farm in Farm.objects.filter(is_active=True).order_by("code"):
        snapshots = close_operating_period(
            farm=farm,
            start_date=start_date,
            end_date=end_date,
            notes=notes,
        )
        results.append({"farm": farm.code, "snapshots": len(snapshots)})
    return results


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def close_tenant_operating_period(
    self,
    schema_name: str,
    start_date: str | None = None,
    end_date: str | None = None,
):
    """Rebuild the P&L snapshots of one tenant.

    Re-running it for the same window overwrites the same snapshot rows, so a
    retry after a broker failure can never double count.
    """
    tenant = Client.objects.get(schema_name=schema_name)
    with tenant_context(tenant):
        farms = _close_farms(
            start_date=start_date,
            end_date=end_date,
            notes=AUTOMATED_CLOSE_NOTE,
        )
    return {"schema": schema_name, "farms": farms}


@shared_task
def close_operating_periods(start_date: str | None = None, end_date: str | None = None):
    """Fan out the period close over every non-public tenant."""
    tenants = (
        Client.objects.exclude(schema_name=get_public_schema_name())
        .order_by("schema_name")
        .values_list("schema_name", flat=True)
    )
    return [
        close_tenant_operating_period(
            schema_name=schema_name,
            start_date=start_date,
            end_date=end_date,
        )
        for schema_name in tenants
    ]
