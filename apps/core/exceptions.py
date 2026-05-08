"""Unified API error envelope.

All errors render as:
    {"error": {"code": "...", "message": "...", "details": ...}}
"""
from rest_framework.views import exception_handler as drf_default_exception_handler


def api_exception_handler(exc, context):
    response = drf_default_exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(data, dict) and "detail" in data:
        detail = data["detail"]
        code = str(getattr(detail, "code", getattr(exc, "default_code", "error")))
        response.data = {"error": {"code": code, "message": str(detail)}}
    elif isinstance(data, dict) and "error" in data:
        # Already in canonical shape (e.g. from a service raising APIException with dict)
        pass
    else:
        response.data = {
            "error": {
                "code": "validation_error",
                "message": "Invalid input.",
                "details": data,
            }
        }
    return response
