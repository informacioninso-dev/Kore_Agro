from .context import AuditContext, reset_audit_context, set_audit_context


class AuditContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip_address = forwarded_for.split(",", 1)[0].strip() or request.META.get("REMOTE_ADDR")
        token = set_audit_context(
            AuditContext(
                actor_id=user.pk if user.is_authenticated else None,
                actor_username=user.get_username() if user.is_authenticated else "",
                request_method=request.method,
                request_path=request.path[:255],
                ip_address=ip_address,
            )
        )
        try:
            return self.get_response(request)
        finally:
            reset_audit_context(token)
