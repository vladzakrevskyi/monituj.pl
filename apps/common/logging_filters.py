import logging
import re

from apps.common.logging_context import request_id_var

_SENSITIVE_PATTERN = re.compile(
    r"(?i)\b(password|token|secret|authorization|cookie|session|api[_-]?key)"
    r"(\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|\S+)"
)


def redact(message: str) -> str:
    return _SENSITIVE_PATTERN.sub(r"\1\2***REDACTED***", message)


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


class RequestIDLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True
