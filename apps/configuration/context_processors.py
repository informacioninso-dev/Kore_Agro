from .access import request_capability_codes, request_profile_codes


def tenant_configuration(request) -> dict:
    return {
        "kore_capabilities": request_capability_codes(request),
        "kore_profiles": request_profile_codes(request),
    }
