from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    """Liveness probe: the web process is able to serve requests."""
    return JsonResponse({"status": "ok"})


@require_GET
def readiness(request):
    """Readiness probe: the process can reach PostgreSQL before accepting traffic."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return JsonResponse({"status": "unavailable", "database": "down"}, status=503)
    return JsonResponse({"status": "ok", "database": "ready"})
