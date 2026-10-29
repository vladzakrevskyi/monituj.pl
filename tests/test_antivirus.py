"""Every upload goes through the antivirus scanner (apps/documents/
antivirus.py) - here a fake clamd speaking the real protocol."""

import io
import socket
import socketserver
import struct
import threading
import zipfile

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.urls import reverse
from PIL import Image

from apps.documents import antivirus
from apps.documents.models import Document
from apps.documents.services import UploadDocumentService
from tests.conftest import make_pdf_upload

# The standard antivirus test file - harmless, every scanner reports it.
EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
MACRO_MARK = b"Attribute VB_Name"


class FakeClamd(socketserver.BaseRequestHandler):
    def _read(self, size):
        data = b""
        while len(data) < size:
            part = self.request.recv(size - len(data))
            if not part:
                raise ConnectionError
            data += part
        return data

    def handle(self):
        command = b""
        while not command.endswith(b"\0"):
            command += self._read(1)
        if command == b"zPING\0":
            self.request.sendall(b"PONG\0")
            return
        content = b""
        while True:
            (length,) = struct.unpack("!L", self._read(4))
            if not length:
                break
            content += self._read(length)
        self.server.scanned.append(content)
        if EICAR in content:
            answer = b"stream: Eicar-Test-Signature FOUND\0"
        elif MACRO_MARK in content:
            answer = b"stream: Heuristics.OLE2.ContainsMacros FOUND\0"
        else:
            answer = b"stream: OK\0"
        self.request.sendall(answer)


@pytest.fixture
def clamd(settings):
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), FakeClamd)
    server.daemon_threads = True
    server.scanned = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    settings.CLAMAV_HOST, settings.CLAMAV_PORT = server.server_address
    settings.SECURITY_ALERTS = True
    settings.SECURITY_EMAIL = "alarm@example.com"
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def scanner_down(settings):
    with socket.socket() as probe:  # a port nobody listens on
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    settings.CLAMAV_HOST, settings.CLAMAV_PORT = "127.0.0.1", port
    settings.SECURITY_ALERTS = True
    settings.SECURITY_EMAIL = "alarm@example.com"


def _upload(client, request_item, upload):
    request_obj = request_item.request
    client.get(reverse("public:request-detail", args=[request_obj.public_token]))
    return client.post(
        reverse(
            "documents_api:upload", args=[request_obj.public_token, request_item.pk]
        ),
        {"file": upload},
    )


def _alarms():
    return [m for m in mail.outbox if m.to == ["alarm@example.com"]]


def _csv(content, name="lista.csv"):
    return SimpleUploadedFile(name, b"nazwa;kwota\nfaktura;100\n" + content)


def _office(name, members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for member, data in members.items():
            archive.writestr(member, data)
    return SimpleUploadedFile(name, buffer.getvalue())


@pytest.mark.django_db
def test_a_clean_file_is_scanned_and_stored(client, request_item, clamd):
    response = _upload(client, request_item, make_pdf_upload())

    assert response.status_code == 201
    assert Document.objects.count() == 1
    assert len(clamd.scanned) == 1
    assert clamd.scanned[0].startswith(b"%PDF")


@pytest.mark.django_db
def test_a_virus_is_refused_and_reported(client, request_item, clamd):
    response = _upload(client, request_item, _csv(EICAR))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VIRUS_FOUND"
    assert not Document.objects.exists()
    [alarm] = _alarms()
    assert "Eicar-Test-Signature" in alarm.subject
    assert f"Prośba: #{request_item.request.pk}" in alarm.body
    assert "acme@example.com" in alarm.body
    # The client is not told the file was stored.
    assert not [m for m in mail.outbox if m.to == ["acme@example.com"]]


@pytest.mark.django_db
def test_a_file_with_macros_is_refused_without_an_alarm(client, request_item, clamd):
    response = _upload(client, request_item, _csv(MACRO_MARK))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "FILE_HAS_MACROS"
    assert "bez makr" in response.json()["error"]["message"]
    assert not Document.objects.exists()
    assert not _alarms()


@pytest.mark.django_db
def test_without_the_scanner_nothing_gets_in(client, request_item, scanner_down):
    response = _upload(client, request_item, make_pdf_upload())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SCANNER_UNAVAILABLE"
    assert not Document.objects.exists()
    [alarm] = _alarms()
    assert "nie odpowiada" in alarm.subject


@pytest.mark.django_db
def test_a_page_photo_is_scanned_before_it_is_decoded(client, request_item, clamd):
    buffer = io.BytesIO()
    Image.new("RGB", (40, 20)).save(buffer, format="JPEG")
    photo = SimpleUploadedFile("strona.jpg", buffer.getvalue() + EICAR)
    request_obj = request_item.request
    client.get(reverse("public:request-detail", args=[request_obj.public_token]))

    response = client.post(
        reverse(
            "documents_api:upload-pages",
            args=[request_obj.public_token, request_item.pk],
        ),
        {"pages": [photo]},
    )

    assert response.json()["error"]["code"] == "VIRUS_FOUND"
    assert not Document.objects.exists()


@pytest.mark.django_db
def test_a_docx_with_a_macro_project_is_refused(request_item):
    upload = _office(
        "umowa.docx",
        {
            "[Content_Types].xml": "<Types/>",
            "word/document.xml": "<w:document/>",
            "word/vbaProject.bin": "macro",
        },
    )

    with pytest.raises(Exception) as exc_info:
        UploadDocumentService.upload_for_item(request_item, upload)
    assert exc_info.value.code == "FILE_HAS_MACROS"


@pytest.mark.django_db
def test_any_zip_renamed_to_xlsx_is_refused(request_item):
    upload = _office("arkusz.xlsx", {"program.exe": "MZ"})

    with pytest.raises(Exception) as exc_info:
        UploadDocumentService.upload_for_item(request_item, upload)
    assert exc_info.value.code == "FILE_DAMAGED"


@pytest.mark.django_db
def test_a_real_office_file_passes(request_item):
    upload = _office(
        "arkusz.xlsx",
        {"[Content_Types].xml": "<Types/>", "xl/workbook.xml": "<workbook/>"},
    )

    document = UploadDocumentService.upload_for_item(request_item, upload)
    assert document.original_filename == "arkusz.xlsx"


@pytest.mark.django_db
def test_files_stored_before_the_scanner_can_be_checked(settings, request_item, clamd):
    host = settings.CLAMAV_HOST
    settings.CLAMAV_HOST = ""  # stored while there was no scanner
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    UploadDocumentService.upload_for_item(request_item, _csv(EICAR, "stare.csv"))
    settings.CLAMAV_HOST = host
    out = io.StringIO()

    call_command("scan_documents", stdout=out)

    assert "Znaleziono: 1." in out.getvalue()
    assert "Eicar-Test-Signature" in out.getvalue()
    assert "stare.csv" in out.getvalue()
    [report] = [m for m in mail.outbox if "Skanowanie plików" in m.subject]
    assert "stare.csv" in report.body
    assert Document.objects.count() == 2  # nothing deleted


def test_scan_documents_needs_the_scanner(scanner_down):
    with pytest.raises(CommandError):
        call_command("scan_documents")


def test_ping(clamd):
    assert antivirus.ping()


def test_production_refuses_to_start_without_the_scanner():
    import os
    import subprocess
    import sys

    from tests.conftest import TEST_ENCRYPTION_KEY

    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.prod",
        "DOCUMENTS_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY,
        "CLAMAV_HOST": "",
        "DJANGO_SECRET_KEY": "x" * 50,
    }
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "CLAMAV_HOST" in result.stderr
