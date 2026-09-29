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


TEST_ENCRYPTION_KEY = "q0uHc4t0Z5a6k8m1T2v3w4x5y6z7A8B9C0D1E2F3G4c="


@pytest.fixture(autouse=True)
def _documents_encrypted(settings):
    """Like production: every stored document is encrypted."""
    settings.DOCUMENTS_ENCRYPTION_KEY = TEST_ENCRYPTION_KEY
    settings.DOCUMENTS_ENCRYPTION_OLD_KEYS = []


@pytest.fixture(autouse=True)
def _no_legal_version_in_force(settings):
    """Nothing to accept unless a test publishes a version: every document
    is dated in the future (tests/test_consents.py sets real dates)."""
    settings.LEGAL_VERSIONS = {key: "2999-01-01" for key in settings.LEGAL_VERSIONS}


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="owner@example.com",
        password="s3cr3t-pass!",
        display_name="Biuro Testowe",
    )


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


@pytest.fixture(autouse=True)
def _stripe_sandbox(settings, monkeypatch):
    """Payments in the sandbox with dummy keys, whatever the local .env says -
    and no test ever reaches the real Stripe API (tests/test_billing.py
    replaces the client with a fake)."""
    from apps.billing import gateway

    settings.STRIPE_MODE = "sandbox"
    settings.STRIPE_KEYS = {
        "sandbox": {"secret_key": "sk_test_dummy", "webhook_secret": "whsec_test"},
        "live": {"secret_key": "", "webhook_secret": ""},
    }
    settings.BILLING_VAT_RATE = 23
    gateway.clear_cache()

    def no_network():
        raise RuntimeError("Stripe called without a fake client")

    monkeypatch.setattr(gateway, "client", no_network)


@pytest.fixture(autouse=True)
def _infakt_off(settings, monkeypatch):
    """No VAT invoices unless a test turns inFakt on - and never a real call
    (tests/test_invoicing.py fakes the API)."""
    import requests

    settings.INFAKT_MODE = "sandbox"
    settings.INFAKT_KEYS = {
        "sandbox": {"api_key": "", "webhook_secret": ""},
        "live": {"api_key": "", "webhook_secret": ""},
    }
    settings.INFAKT_SEND_TO_KSEF = False
    # No GUS either (tests/test_billing_profile.py turns it on with a fake).
    settings.GUS_MODE = "production"
    settings.GUS_API_KEY = ""

    def no_network(*args, **kwargs):
        raise RuntimeError("inFakt called without a fake")

    monkeypatch.setattr(requests, "request", no_network)
