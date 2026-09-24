import base64

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.clients.models import Client
from apps.documents.storage import private_storage
from apps.requests.models import Request, RequestItem

MINIMAL_PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
MINIMAL_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+A8A"
    "AQUBAScY42YAAAAASUVORK5CYII="
)
FAKE_EXE_BYTES = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00" + b"\x00" * 50


def page_text(response):
    """Decoded page with the typography non-breaking spaces turned back into
    plain ones, so tests can look for phrases as written in templates."""
    return response.content.decode().replace("\u00a0", " ")


def make_pdf_upload(name="dokument.pdf"):
    return SimpleUploadedFile(name, MINIMAL_PDF_BYTES, content_type="application/pdf")


def make_png_upload(name="obraz.png"):
    return SimpleUploadedFile(name, MINIMAL_PNG_BYTES, content_type="image/png")


def make_fake_exe_upload(name="dokument.pdf"):
    return SimpleUploadedFile(name, FAKE_EXE_BYTES, content_type="application/pdf")


@pytest.fixture(autouse=True)
def _isolate_document_storage(tmp_path, monkeypatch):
    monkeypatch.setitem(private_storage.__dict__, "location", str(tmp_path))
    monkeypatch.setitem(private_storage.__dict__, "base_location", str(tmp_path))


@pytest.fixture
def user(db):
    return User.objects.create_user(email="owner@example.com", password="s3cr3t-pass!")


@pytest.fixture
def client_record(db, user):
    return Client.objects.create(
        owner=user, name="Acme Sp. z o.o.", email="acme@example.com"
    )


@pytest.fixture
def request_record(db, user, client_record):
    return Request.objects.create(
        client=client_record, created_by=user, name="Dokumenty za wrzesien"
    )


@pytest.fixture
def request_item(db, request_record):
    return RequestItem.objects.create(request=request_record, name="Faktury sprzedaży")
