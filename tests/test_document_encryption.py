import os
import subprocess
import sys

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.urls import reverse

from apps.audit.models import AuditEvent, AuditLog
from apps.documents import encryption
from apps.documents.encryption import MAGIC, DecryptionError
from apps.documents.models import Document
from apps.documents.services import UploadDocumentService
from apps.documents.storage import private_storage, read_document_file
from tests.conftest import MINIMAL_PDF_BYTES, TEST_ENCRYPTION_KEY, make_pdf_upload


def _on_disk(document):
    with private_storage.open(document.storage_key, "rb") as handle:
        return handle.read()


@pytest.fixture
def document(request_item):
    return UploadDocumentService.upload_for_item(request_item, make_pdf_upload())


@pytest.mark.django_db
def test_file_on_disk_is_encrypted(document):
    stored = _on_disk(document)

    assert stored.startswith(MAGIC)
    assert b"%PDF" not in stored
    assert document.wrapped_key
    assert document.encryption_key_id == encryption.current_key_id()
    assert read_document_file(document) == MINIMAL_PDF_BYTES


@pytest.mark.django_db
def test_changed_file_is_refused(document):
    stored = bytearray(_on_disk(document))
    stored[-1] ^= 1
    private_storage.delete(document.storage_key)
    private_storage.save(document.storage_key, ContentFile(bytes(stored)))

    with pytest.raises(DecryptionError):
        read_document_file(document)


@pytest.mark.django_db
def test_file_moved_to_another_document_does_not_open(request_item):
    """Swapping encrypted files between documents on disk gets nowhere: the
    path is part of what is authenticated."""
    first = UploadDocumentService.upload_for_item(
        request_item, make_pdf_upload("a.pdf")
    )
    from tests.conftest import make_png_upload

    second = UploadDocumentService.upload_for_item(request_item, make_png_upload())
    first_blob = _on_disk(first)
    private_storage.delete(second.storage_key)
    private_storage.save(second.storage_key, ContentFile(first_blob))
    second.wrapped_key = first.wrapped_key

    with pytest.raises(DecryptionError):
        read_document_file(second)


@pytest.mark.django_db
def test_without_the_right_master_key_nothing_opens(document, settings):
    settings.DOCUMENTS_ENCRYPTION_KEY = encryption.generate_key()

    with pytest.raises(DecryptionError):
        read_document_file(document)


@pytest.mark.django_db
def test_unreadable_file_gives_a_clear_error(client, user, document):
    private_storage.delete(document.storage_key)
    private_storage.save(document.storage_key, ContentFile(MAGIC + b"garbage" * 5))
    client.force_login(user)

    response = client.get(reverse("documents_api:download", args=[document.pk]))

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "FILE_UNREADABLE"


@pytest.mark.django_db
def test_owner_gets_the_original_bytes(client, user, document):
    client.force_login(user)

    response = client.get(reverse("documents_api:download", args=[document.pk]))

    assert b"".join(response.streaming_content) == MINIMAL_PDF_BYTES


# --- files from before encryption --------------------------------------------


@pytest.fixture
def plaintext_document(request_item):
    key = "2026/01/01/legacy0000000000000000000000000.pdf"
    private_storage.save(key, ContentFile(MINIMAL_PDF_BYTES))
    return Document.objects.create(
        request_item=request_item,
        storage_key=key,
        original_filename="stary.pdf",
        content_type="application/pdf",
        size=len(MINIMAL_PDF_BYTES),
        checksum="x",
    )


@pytest.mark.django_db
def test_old_plaintext_files_still_open_and_can_be_encrypted(plaintext_document):
    old_key = plaintext_document.storage_key
    assert read_document_file(plaintext_document) == MINIMAL_PDF_BYTES

    call_command("encrypt_documents")
    call_command("encrypt_documents")  # nothing left the second time

    plaintext_document.refresh_from_db()
    assert plaintext_document.storage_key != old_key
    assert not private_storage.exists(old_key)
    assert _on_disk(plaintext_document).startswith(MAGIC)
    assert read_document_file(plaintext_document) == MINIMAL_PDF_BYTES


# --- rotating the master key -----------------------------------------------


@pytest.mark.django_db
def test_master_key_rotation(document, settings):
    old_id = document.encryption_key_id
    settings.DOCUMENTS_ENCRYPTION_KEY = encryption.generate_key()
    settings.DOCUMENTS_ENCRYPTION_OLD_KEYS = [TEST_ENCRYPTION_KEY]
    assert read_document_file(document) == MINIMAL_PDF_BYTES

    call_command("rewrap_document_keys")
    settings.DOCUMENTS_ENCRYPTION_OLD_KEYS = []
    document.refresh_from_db()

    assert document.encryption_key_id != old_id
    assert read_document_file(document) == MINIMAL_PDF_BYTES


@pytest.mark.parametrize("bad", ["not base64!!", "c2hvcnQ="])
def test_malformed_master_key_is_refused(settings, bad):
    settings.DOCUMENTS_ENCRYPTION_KEY = bad

    with pytest.raises(ImproperlyConfigured):
        encryption.enabled()


def test_generated_keys_are_256_bit(capsys):
    call_command("generate_encryption_key")
    key = capsys.readouterr().out.strip()

    assert len(encryption._decode(key, "key")) == 32


def test_production_refuses_to_start_without_a_key():
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.prod",
        "DOCUMENTS_ENCRYPTION_KEY": "",
        "DJANGO_SECRET_KEY": "x" * 50,
    }
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "DOCUMENTS_ENCRYPTION_KEY" in result.stderr


# --- who downloaded ------------------------------------------------------------


@pytest.mark.django_db
def test_downloads_are_recorded_in_the_request_history(client, user, request_item):
    page = reverse("public:request-detail", args=[request_item.request.public_token])
    client.get(page)
    upload = client.post(
        reverse(
            "documents_api:upload",
            args=[request_item.request.public_token, request_item.pk],
        ),
        {"file": make_pdf_upload()},
    )
    document_id = upload.json()["data"]["document"]["id"]
    client.get(reverse("documents_api:download", args=[document_id]))
    client.force_login(user)
    client.get(reverse("documents_api:download", args=[document_id]))

    downloads = AuditLog.objects.filter(event=AuditEvent.FILE_DOWNLOAD)
    history = client.get(reverse("requests:detail", args=[request_item.request_id]))
    text = history.content.decode().replace(" ", " ")

    assert sorted(d.metadata["by"] for d in downloads) == ["owner", "recipient"]
    assert all(d.ip_address for d in downloads)
    assert "Pobrano dokument (odbiorca)" in text
    assert "Pobrano dokument (Ty)" in text


@pytest.mark.django_db
def test_refused_download_is_not_recorded_as_one(client, document):
    client.get(reverse("documents_api:download", args=[document.pk]))

    assert not AuditLog.objects.filter(event=AuditEvent.FILE_DOWNLOAD).exists()
