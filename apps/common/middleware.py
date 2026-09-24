import logging
import uuid

from django.conf import settings

from apps.common.exceptions import ApplicationError
from apps.common.logging_context import request_id_var
from apps.common.responses import error_response

logger = logging.getLogger("monituj")


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = str(uuid.uuid4())
        token = request_id_var.set(request.request_id)
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response["X-Request-ID"] = request.request_id
        return response


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.csp_header = "; ".join(
            f"{directive} {value}"
            for directive, value in settings.CONTENT_SECURITY_POLICY.items()
        )
        self.permissions_policy_header = ", ".join(
            f"{feature}={value}"
            for feature, value in settings.PERMISSIONS_POLICY.items()
        )

    def __call__(self, request):
        response = self.get_response(request)
        response["Content-Security-Policy"] = self.csp_header
        response["Permissions-Policy"] = self.permissions_policy_header
        return response


class ApiExceptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if not request.path.startswith("/api/"):
            return None

        if isinstance(exception, ApplicationError):
            logger.warning(
                "Handled API error: %s",
                exception.code,
                extra={"request_id": request.request_id, "path": request.path},
            )
            return error_response(
                exception.code, exception.message, status=exception.status_code
            )

        logger.exception(
            "Unhandled exception in API view",
            extra={"request_id": request.request_id, "path": request.path},
        )
        return error_response(
            "INTERNAL_ERROR", "Wystąpił błąd. Spróbuj ponownie później.", status=500
        )
