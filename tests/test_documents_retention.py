from datetime import timedelta

import pytest
from django.core import mail
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.accounts.services import GuestOwnerService
from apps.audit.models import AuditEvent, AuditLog
from apps.clients.models import Client
from apps.common.exceptions import NotFoundAppError
from apps.documents.models import Document
from apps.documents.retention import DocumentRetentionService
from apps.documents.services import DocumentAccessService, UploadDocumentService
from apps.documents.storage import private_storage
from apps.requests.models import Request, RequestItem
from tests.conftest import make_pdf_upload, page_text


def _upload(request_item, days_ago):
    document = UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    Document.objects.filter(pk=document.pk).update(
        uploaded_at=timezone.now() - timedelta(days=days_ago)
    )
    document.refresh_from_db()
    return document


@pytest.mark.django_db
def test_expired_document_is_anonymized_and_file_deleted(request_record, request_item):
    request_record.retention_days = 30
    request_record.save()
    document = _upload(request_item, days_ago=31)
    storage_key = document.storage_key
    assert private_storage.exists(storage_key)

    count = DocumentRetentionService.anonymize_expired()

    document.refresh_from_db()
    assert count == 1
    assert document.is_anonymized
    assert document.original_filename == ""
    assert document.checksum == ""
    assert document.size == 0
    assert not private_storage.exists(storage_key)
    assert AuditLog.objects.filter(event=AuditEvent.DOCUMENTS_ANONYMIZED).exists()


@pytest.mark.django_db
def test_document_within_retention_is_kept(request_record, request_item):
    request_record.retention_days = 30
    request_record.save()
    document = _upload(request_item, days_ago=29)

    assert DocumentRetentionService.anonymize_expired() == 0
    document.refresh_from_db()
    assert not document.is_anonymized


@pytest.mark.django_db
def test_anonymization_notifies_owner_and_recipient_once_per_request(
    request_record, request_item
):
    request_record.retention_days = 10
    request_record.save()
    second_item = RequestItem.objects.create(request=request_record, name="Umowa")
    _upload(request_item, days_ago=11)
    _upload(second_item, days_ago=12)
    mail.outbox.clear()

    DocumentRetentionService.anonymize_expired()

    recipients = sorted(m.to[0] for m in mail.outbox)
    assert recipients == ["acme@example.com", "owner@example.com"]
    assert all("2" in m.body for m in mail.outbox)


@pytest.mark.django_db
def test_guest_requests_notify_only_the_recipient():
    owner = GuestOwnerService.get_or_create()
    client = Client.objects.create(owner=owner, name="Odbiorca", email="o@example.com")
    request_obj = Request.objects.create(
        client=client, created_by=owner, name="Gosc", retention_days=1
    )
    item = RequestItem.objects.create(request=request_obj, name="A")
    _upload(item, days_ago=2)
    mail.outbox.clear()

    DocumentRetentionService.anonymize_expired()

    assert [m.to for m in mail.outbox] == [["o@example.com"]]


@pytest.mark.django_db
def test_anonymized_document_cannot_be_downloaded(user, request_record, request_item):
    request_record.retention_days = 1
    request_record.save()
    document = _upload(request_item, days_ago=2)
    DocumentRetentionService.anonymize_expired()

    request = RequestFactory().get("/")
    request.user = user
    with pytest.raises(NotFoundAppError):
        DocumentAccessService.get_for_download(document.pk, request)


@pytest.mark.django_db
def test_request_detail_shows_placeholder_for_anonymized_file(
    client, user, request_record, request_item
):
    request_record.retention_days = 1
    request_record.save()
    _upload(request_item, days_ago=2)
    DocumentRetentionService.anonymize_expired()
    client.force_login(user)

    response = client.get(reverse("requests:detail", args=[request_record.pk]))

    assert "Plik usunięty po okresie przechowywania" in page_text(response)
    assert b"dokument.pdf" not in response.content
