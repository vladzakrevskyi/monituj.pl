import pytest
from django.db import IntegrityError, transaction

from apps.documents.models import Document, DocumentStatus


@pytest.mark.django_db
def test_document_defaults_to_uploaded_status(request_item):
    document = Document.objects.create(
        request_item=request_item,
        storage_key="2026/09/22/abc123.pdf",
        original_filename="faktura.pdf",
        content_type="application/pdf",
        size=1024,
        checksum="a" * 64,
    )

    assert document.status == DocumentStatus.UPLOADED
    assert str(document) == "faktura.pdf"


@pytest.mark.django_db
def test_storage_key_must_be_unique(request_item):
    Document.objects.create(
        request_item=request_item,
        storage_key="dup-key.pdf",
        original_filename="a.pdf",
        content_type="application/pdf",
        size=10,
        checksum="a" * 64,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Document.objects.create(
                request_item=request_item,
                storage_key="dup-key.pdf",
                original_filename="b.pdf",
                content_type="application/pdf",
                size=20,
                checksum="b" * 64,
            )


@pytest.mark.django_db
def test_document_can_exist_without_request_item():
    document = Document.objects.create(
        request_item=None,
        storage_key="standalone.pdf",
        original_filename="standalone.pdf",
        content_type="application/pdf",
        size=10,
        checksum="a" * 64,
    )

    assert document.request_item is None
