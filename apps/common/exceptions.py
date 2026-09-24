class ApplicationError(Exception):
    code = "APPLICATION_ERROR"
    status_code = 400

    def __init__(self, message, code=None, status_code=None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class ValidationAppError(ApplicationError):
    code = "VALIDATION_ERROR"
    status_code = 400


class NotFoundAppError(ApplicationError):
    code = "NOT_FOUND"
    status_code = 404


class PermissionDeniedAppError(ApplicationError):
    code = "PERMISSION_DENIED"
    status_code = 403


class RateLimitedAppError(ApplicationError):
    code = "RATE_LIMITED"
    status_code = 429
