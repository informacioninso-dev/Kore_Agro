from decimal import Decimal
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context, tenant_context

from apps.configuration.models import OrganizationCapability
from apps.finance.models import CostAllocation
from apps.herd.models import Farm
from apps.sync.services import ActionEventMessage, process_action_event
from apps.workforce.models import Worker, WorkLog, WorkTask
from apps.workforce.services import complete_task
from tests.factories import authenticated_manager_client, create_tenant, seed_farm


@pytest.mark.django_db(transaction=True)
def test_completing_task_books_work_log_and_labor_cost():
    tenant = create_tenant("workforcecost")
    with tenant_context(tenant):
        farm, group, _, _, _ = seed_farm()
        worker = Worker.objects.create(
            farm=farm,
            code="W-01",
            full_name="Maria Campo",
            position=Worker.Position.LIVESTOCK,
            hourly_rate=Decimal("3.50"),
        )
        task = WorkTask.objects.create(
            farm=farm,
            title="Revisar cerca",
            category=WorkTask.Category.MAINTENANCE,
            assigned_to=worker,
            group=group,
        )

        log = complete_task(task, worker=worker, hours=Decimal("2.25"))
        task.refresh_from_db()

        assert task.status == WorkTask.Status.COMPLETED
        assert log.labor_cost == Decimal("7.8750")
        assert log.cost_allocation.cost_type == CostAllocation.CostType.LABOR
        assert log.cost_allocation.group == group
        assert log.cost_allocation.amount == Decimal("7.8750")


@pytest.mark.django_db(transaction=True)
def test_task_rejects_worker_from_another_farm():
    tenant = create_tenant("workforcefarm")
    with tenant_context(tenant):
        farm, _, _, _, _ = seed_farm()
        other_farm = Farm.objects.create(name="Hacienda vecina", code="WF-VECINA")
        worker = Worker.objects.create(
            farm=other_farm,
            code="W-02",
            full_name="Trabajador Vecino",
        )
        task = WorkTask.objects.create(
            farm=farm,
            title="Tarea local",
            category=WorkTask.Category.OTHER,
        )

        with pytest.raises(ValidationError, match="no esta activo"):
            complete_task(task, worker=worker, hours=Decimal("1"))


@pytest.mark.django_db(transaction=True)
def test_manager_creates_worker_task_and_completes_it():
    tenant = create_tenant("workforceweb")
    with tenant_context(tenant):
        farm, group, _, _, _ = seed_farm()
    client = authenticated_manager_client(tenant)
    today = timezone.localdate().isoformat()

    worker_response = client.post(
        "/trabajo/personal/crear/",
        {
            "farm": str(farm.id),
            "code": "TR-01",
            "full_name": "Luis Prado",
            "position": Worker.Position.FOREMAN,
            "phone": "0990000000",
            "hourly_rate": "4.25",
            "hired_on": today,
            "user": "",
            "notes": "",
        },
    )
    assert worker_response.status_code == 200
    assert "Trabajador Luis Prado creado" in worker_response.content.decode()
    with tenant_context(tenant):
        worker = Worker.objects.get(code="TR-01")

    task_response = client.post(
        "/trabajo/tareas/crear/",
        {
            "farm": str(farm.id),
            "title": "Limpiar saladero",
            "category": WorkTask.Category.MAINTENANCE,
            "priority": WorkTask.Priority.HIGH,
            "assigned_to": str(worker.id),
            "scheduled_for": today,
            "due_time": "10:30",
            "estimated_hours": "1.50",
            "group": str(group.id),
            "animal": "",
            "paddock": "",
            "instructions": "Retirar material viejo.",
        },
    )
    assert task_response.status_code == 200
    with tenant_context(tenant):
        task = WorkTask.objects.get(title="Limpiar saladero")

    complete_response = client.post(
        "/trabajo/tareas/accion/",
        {
            "farm": str(farm.id),
            "task": str(task.id),
            "action": "complete",
            "worker": str(worker.id),
            "hours": "1.25",
            "notes": "Trabajo terminado",
        },
    )
    assert complete_response.status_code == 200
    assert "costo laboral" in complete_response.content.decode()
    with tenant_context(tenant):
        assert WorkLog.objects.get(task=task).labor_cost == Decimal("5.3125")


@pytest.mark.django_db(transaction=True)
def test_workforce_route_requires_capability():
    tenant = create_tenant("workforceaccess")
    client = authenticated_manager_client(tenant)
    with schema_context(get_public_schema_name()):
        assignment = OrganizationCapability.objects.get(
            organization=tenant,
            capability__code="workforce",
        )
        assignment.status = OrganizationCapability.Status.SUSPENDED
        assignment.save(update_fields=["status"])

    response = client.get("/trabajo/")
    home_response = client.get("/")

    assert response.status_code == 403
    assert "Personal y tareas" not in home_response.content.decode()


@pytest.mark.django_db(transaction=True)
def test_offline_task_completion_is_idempotent_and_books_cost():
    tenant = create_tenant("workforcesync")
    with tenant_context(tenant):
        farm, _, _, _, _ = seed_farm()
        worker = Worker.objects.create(
            farm=farm,
            code="SYNC-01",
            full_name="Operador Offline",
            hourly_rate=Decimal("5"),
        )
        task = WorkTask.objects.create(
            farm=farm,
            title="Inspeccion offline",
            category=WorkTask.Category.LIVESTOCK,
            assigned_to=worker,
        )
        message = ActionEventMessage(
            event_id=uuid4(),
            device_id=uuid4(),
            actor_id=None,
            tenant_id=None,
            client_sequence=1,
            schema_version=1,
            event_type="workforce.task_completed",
            occurred_at=timezone.now(),
            payload={
                "farm_id": str(farm.id),
                "task_id": str(task.id),
                "worker_id": str(worker.id),
                "hours": "2",
                "notes": "Completada sin conexion",
            },
        )

        first = process_action_event(message)
        second = process_action_event(message)

        assert first.status == "acked"
        assert second.status == "acked"
        assert second.detail == "already_processed"
        assert WorkLog.objects.get().labor_cost == Decimal("10.0000")
        assert CostAllocation.objects.get().source_event_id == message.event_id
