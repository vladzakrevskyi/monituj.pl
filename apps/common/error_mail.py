"""Errors emailed to the team (settings.ADMINS) - a crash on a page, a
failed background task, anything logged at ERROR by Monituj itself.

Unlike Django's own AdminEmailHandler, the email says what failed and where
(the message, the traceback, the URL, the user id) but never carries the
request's data or local variables: those can hold clients' personal data.
The same error goes out at most once per THROTTLE, and no more than
MAX_PER_HOUR emails an hour from one process - an outage must not flood the
inbox."""

import logging
import traceback

from django.conf import settings
from django.core.cache import cache
from django.core.mail import mail_admins
from django.utils import timezone

THROTTLE = 10 * 60
MAX_PER_HOUR = 20


def _fingerprint(record):
    """What makes two errors "the same": the logger, the exception type and
    the line it was raised at - or the message, without an exception."""
    if record.exc_info and record.exc_info[1] is not None:
        exc_type, _exc, tb = record.exc_info
        frames = traceback.extract_tb(tb)
        where = f"{frames[-1].filename}:{frames[-1].lineno}" if frames else ""
        return f"{record.name}:{exc_type.__name__}:{where}"
    return f"{record.name}:{record.getMessage()[:200]}"


def _allowed(record):
    try:
        if not cache.add(f"error-mail:{hash(_fingerprint(record))}", 1, THROTTLE):
            return False
        hour = f"error-mail-hour:{timezone.now():%Y%m%d%H}"
        cache.add(hour, 0, 3600)
        return cache.incr(hour) <= MAX_PER_HOUR
    except Exception:
        return True  # no cache: better an email too many than none


def _body(record, handler):
    lines = [
        f"Czas: {timezone.localtime():%Y-%m-%d %H:%M:%S}",
        f"Logger: {record.name}",
        f"Wiadomość: {record.getMessage()}",
    ]
    request = getattr(record, "request", None)
    if request is not None:
        lines.append(f"Adres: {request.method} {request.path}")
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            lines.append(f"Użytkownik (id): {user.pk}")
    request_id = getattr(record, "request_id", "")
    if request_id and request_id != "-":
        lines.append(f"Request id: {request_id}")
    if record.exc_info:
        lines += ["", handler.formatter_for_traceback.formatException(record.exc_info)]
    lines += ["", "Szczegóły w logach: docker compose logs --tail 200 web worker"]
    return "\n".join(lines)


class ErrorEmailHandler(logging.Handler):
    formatter_for_traceback = logging.Formatter()

    def __init__(self):
        super().__init__(level=logging.ERROR)

    def emit(self, record):
        try:
            if settings.DEBUG or not settings.ADMINS or not _allowed(record):
                return
            summary = record.getMessage().splitlines()[0] if record.getMessage() else ""
            mail_admins(f"Błąd: {summary[:120]}", _body(record, self))
        except Exception:
            self.handleError(record)
