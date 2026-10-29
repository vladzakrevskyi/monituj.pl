"""Antivirus check of every uploaded file - ClamAV's clamd (deploy/clamav/).

Files come from people outside the office - a forwarded link is enough to
send one - and the office opens them on its own computers. So each file
goes to clamd before it is encrypted and stored (validate_upload):
- a virus is refused, and the owner of the site gets an alarm;
- an Office file with macros is refused too (AlertOLE2Macros in
  clamd.conf): the commonest way malware reaches an office, and nothing a
  client needs to send - a PDF or a plain .xlsx says the same.

clamd's INSTREAM over TCP: the file in chunks, each after its length in
4 bytes, ended by a zero length; the answer is "stream: OK" or
"stream: <name> FOUND". Without CLAMAV_HOST (local work) nothing is
checked; production requires it (settings/prod.py), and a scanner that
doesn't answer refuses the upload - a file never gets in unchecked.
"""

import logging
import socket
import struct

from django.conf import settings

from apps.common import security_watch
from apps.common.exceptions import ValidationAppError

logger = logging.getLogger("monituj")

CHUNK = 64 * 1024
# clamd pauses scanning while it reloads its signatures (deploy/clamav/
# clamd.conf, ConcurrentDatabaseReload no) - wait that out.
TIMEOUT = 90
MACROS = "Heuristics.OLE2.ContainsMacros"

VIRUS_MESSAGE = (
    "Plik został zablokowany przez skaner antywirusowy. Jeśli to Twój "
    "dokument, sprawdź komputer programem antywirusowym i wyślij plik ponownie."
)
MACROS_MESSAGE = (
    "Plik zawiera makra, więc ze względów bezpieczeństwa go nie przyjmujemy. "
    "Zapisz go jako PDF albo jako zwykły plik .xlsx / .docx (bez makr) i "
    "wyślij ponownie."
)
UNAVAILABLE_MESSAGE = (
    "Nie możemy teraz sprawdzić pliku. Spróbuj ponownie za kilka minut."
)


class ScannerUnavailable(Exception):
    """clamd didn't answer, or answered with an error."""


def enabled():
    return bool(settings.CLAMAV_HOST)


def _connect():
    return socket.create_connection(
        (settings.CLAMAV_HOST, settings.CLAMAV_PORT), timeout=TIMEOUT
    )


def _answer(connection):
    data = b""
    while not data.endswith(b"\0"):
        part = connection.recv(4096)
        if not part:
            break
        data += part
    return data.rstrip(b"\0").decode("utf-8", "replace").strip()


def scan(content):
    """None for a clean file, else the name of what was found. Raises
    ScannerUnavailable."""
    try:
        with _connect() as connection:
            connection.sendall(b"zINSTREAM\0")
            for start in range(0, len(content), CHUNK):
                chunk = content[start : start + CHUNK]
                connection.sendall(struct.pack("!L", len(chunk)) + chunk)
            connection.sendall(struct.pack("!L", 0))
            answer = _answer(connection)
    except OSError as exc:
        raise ScannerUnavailable(f"{type(exc).__name__}: {exc}") from exc
    if answer == "stream: OK":
        return None
    if answer.startswith("stream: ") and answer.endswith(" FOUND"):
        return answer.removeprefix("stream: ").removesuffix(" FOUND").strip()
    # "INSTREAM size limit exceeded. ERROR" and the like.
    raise ScannerUnavailable(answer or "empty answer")


def ping():
    """Does clamd answer? (post_deploy)"""
    try:
        with _connect() as connection:
            connection.sendall(b"zPING\0")
            return _answer(connection) == "PONG"
    except OSError:
        return False


def _about(file_name, size, request_obj):
    lines = [f"Plik: {file_name} ({size} B)"]
    if request_obj is not None:
        lines += [
            f"Prośba: #{request_obj.pk} „{request_obj.name}”",
            f"Nadawca (konto): {request_obj.created_by.email}",
            f"Odbiorca: {request_obj.client.email}",
        ]
    return lines


def check(content, file_name, request_obj=None):
    """Refuses a file with a virus or macros (ValidationAppError); a virus
    and a scanner that doesn't answer also raise the alarm."""
    if not enabled():
        return
    try:
        found = scan(content)
    except ScannerUnavailable as exc:
        logger.error("Antivirus scanner unavailable: %s", exc)
        security_watch.alert(
            "skaner antywirusowy nie odpowiada",
            [
                f"Błąd: {exc}",
                "Klienci nie mogą teraz przesyłać plików.",
                "Sprawdź: docker compose -f docker-compose.prod.yml ps clamav "
                "i logs clamav.",
            ],
            key="antivirus-unavailable",
            advice="",
        )
        raise ValidationAppError(
            UNAVAILABLE_MESSAGE, code="SCANNER_UNAVAILABLE", status_code=503
        ) from exc
    if found is None:
        return
    if found.startswith(MACROS):
        logger.info("Upload refused: Office file with macros (%s)", file_name)
        raise ValidationAppError(MACROS_MESSAGE, code="FILE_HAS_MACROS")
    logger.warning("Upload refused: %s in %s", found, file_name)
    security_watch.alert(
        f"zablokowano plik z wirusem ({found})",
        [
            f"Wykryto: {found}",
            *_about(file_name, len(content), request_obj),
            "Plik nie został zapisany. Jeśli takie pliki powtarzają się w jednej "
            "prośbie, link mógł trafić w niepowołane ręce - zamknij prośbę.",
        ],
        key=f"virus:{found}:{getattr(request_obj, 'pk', '')}",
        advice="",
    )
    raise ValidationAppError(VIRUS_MESSAGE, code="VIRUS_FOUND")
