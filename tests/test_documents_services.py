import pytest
from django.core import mail
from django.test import RequestFactory

from apps.accounts.models import User
from apps.audit.models import AuditEvent, AuditLog
from apps.common.exceptions import (
    NotFoundAppError,
    PermissionDeniedAppError,
    ValidationAppError,
)
from apps.documents.models import Document, DocumentStatus
from apps.documents.services import (
    DocumentAccessService,
    DocumentReviewService,
    GuestDeleteService,
    UploadDocumentService,
)
from apps.requests.models import RequestItemStatus
from apps.requests.services import RequestService
from tests.conftest import make_pdf_upload


def _django_request():
    request = RequestFactory().get("/d/token/")
    from django.contrib.sessions.middleware import SessionMiddleware

    SessionMiddleware(lambda r: None).process_request(request)
    request.request_id = "req-doc"
    return request


@pytest.mark.django_db
def test_upload_for_item_marks_item_delivered_and_sends_confirmation(request_item):
    document = UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    request_item.refresh_from_db()

    assert request_item.status == RequestItemStatus.DOSTARCZONY
    assert document.request_item_id == request_item.pk
    assert any(m.subject for m in mail.outbox if "Potwierdzenie" in m.subject)
    assert AuditLog.objects.filter(event=AuditEvent.DOCUMENT_UPLOADED).exists()


@pytest.mark.django_db
def test_upload_for_item_rejects_when_already_accepted(request_item):
    request_item.status = RequestItemStatus.ZAAKCEPTOWANY
    request_item.save()

    with pytest.raises(ValidationAppError) as exc_info:
        UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    assert exc_info.value.code == "ITEM_ALREADY_ACCEPTED"


@pytest.mark.django_db
def test_upload_for_item_rejects_duplicate_checksum(request_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())

    with pytest.raises(ValidationAppError) as exc_info:
        UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    assert exc_info.value.code == "DUPLICATE_FILE"


@pytest.mark.django_db
def test_upload_sends_complete_email_once_all_items_delivered(user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Dokumenty",
        description="",
        deadline=None,
        item_names=["A", "B"],
    )
    items = list(request_obj.items.all())

    UploadDocumentService.upload_for_item(items[0], make_pdf_upload(name="a.pdf"))
    assert not any("Komplet" in (m.subject or "") for m in mail.outbox)

    UploadDocumentService.upload_for_item(items[1], make_pdf_upload(name="b.pdf"))
    complete_emails = [m for m in mail.outbox if "Komplet" in (m.subject or "")]
    # One thank-you to the recipient, one "you have everything" to the sender.
    assert sorted(m.to[0] for m in complete_emails) == [
        client_record.email,
        user.email,
    ]


@pytest.mark.django_db
def test_accept_marks_item_and_documents(request_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())

    DocumentReviewService.accept(request_item)
    request_item.refresh_from_db()

    assert request_item.status == RequestItemStatus.ZAAKCEPTOWANY
    assert (
        Document.objects.get(request_item=request_item).status
        == DocumentStatus.ACCEPTED
    )


@pytest.mark.django_db
def test_reject_requires_non_empty_reason(request_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())

    with pytest.raises(ValidationAppError) as exc_info:
        DocumentReviewService.reject(request_item, "   ")
    assert exc_info.value.code == "REASON_REQUIRED"


@pytest.mark.django_db
def test_accept_rejects_item_that_was_never_delivered(request_item):
    with pytest.raises(ValidationAppError) as exc_info:
        DocumentReviewService.accept(request_item)
    assert exc_info.value.code == "ITEM_NOT_DELIVERED"


@pytest.mark.django_db
def test_reject_rejects_item_that_was_never_delivered(request_item):
    with pytest.raises(ValidationAppError) as exc_info:
        DocumentReviewService.reject(request_item, "Powód")
    assert exc_info.value.code == "ITEM_NOT_DELIVERED"


@pytest.mark.django_db
def test_accept_rejects_already_accepted_item(request_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    DocumentReviewService.accept(request_item)

    with pytest.raises(ValidationAppError) as exc_info:
        DocumentReviewService.accept(request_item)
    assert exc_info.value.code == "ITEM_NOT_DELIVERED"


@pytest.mark.django_db
def test_reject_sets_reason_and_sends_email(request_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    mail.outbox.clear()

    DocumentReviewService.reject(request_item, "Nieczytelny skan")
    request_item.refresh_from_db()

    assert request_item.status == RequestItemStatus.ODRZUCONY
    assert request_item.rejection_reason == "Nieczytelny skan"
    assert any("Nieczytelny skan" in (m.body or "") for m in mail.outbox)


@pytest.mark.django_db
def test_download_allows_owner(user, request_item):
    document = UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    request = _django_request()
    request.user = user

    found = DocumentAccessService.get_for_download(document.pk, request)
    assert found.pk == document.pk


@pytest.mark.django_db
def test_download_denies_other_authenticated_user(request_item):
    document = UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    other = User.objects.create_user(email="stranger@example.com", password="x")
    request = _django_request()
    request.user = other

    with pytest.raises(PermissionDeniedAppError):
        DocumentAccessService.get_for_download(document.pk, request)


@pytest.mark.django_db
def test_download_denies_guest_who_never_visited_the_public_page(request_item):
    """Sequential document IDs are guessable; an unprotected request must not
    become downloadable to a guest who never proved knowledge of its
    unguessable public token (§7/§33)."""
    document = UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    from django.contrib.auth.models import AnonymousUser

    request = _django_request()
    request.user = AnonymousUser()

    with pytest.raises(PermissionDeniedAppError):
        DocumentAccessService.get_for_download(document.pk, request)


@pytest.mark.django_db
def test_download_allows_guest_after_visiting_unprotected_public_page(request_item):
    from django.contrib.auth.models import AnonymousUser

    from apps.requests.services import PublicAccessService

    document = UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    request = _django_request()
    request.user = AnonymousUser()
    PublicAccessService.grant_access(request_item.request, request)

    found = DocumentAccessService.get_for_download(document.pk, request)
    assert found.pk == document.pk


@pytest.mark.django_db
def test_download_denies_guest_when_request_protected_and_locked(user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
        password="Sekretne-Haslo!1",
    )
    item = request_obj.items.first()
    document = UploadDocumentService.upload_for_item(item, make_pdf_upload())
    from django.contrib.auth.models import AnonymousUser

    request = _django_request()
    request.user = AnonymousUser()

    with pytest.raises(PermissionDeniedAppError):
        DocumentAccessService.get_for_download(document.pk, request)


@pytest.mark.django_db
def test_download_raises_not_found_for_standalone_document():
    document = Document.objects.create(
        request_item=None,
        storage_key="standalone-download-test.pdf",
        original_filename="standalone.pdf",
        content_type="application/pdf",
        size=10,
        checksum="a" * 64,
    )
    from django.contrib.auth.models import AnonymousUser

    request = _django_request()
    request.user = AnonymousUser()

    with pytest.raises(NotFoundAppError):
        DocumentAccessService.get_for_download(document.pk, request)


@pytest.mark.django_db
def test_guest_can_delete_own_upload_and_item_reverts_to_brak(request_item):
    upload_request = _django_request()
    upload_request.session.save()

    document = UploadDocumentService.upload_for_item(
        request_item, make_pdf_upload(), django_request=upload_request
    )
    assert document.uploaded_by_session_key == upload_request.session.session_key

    item = GuestDeleteService.delete_own_upload(document.pk, upload_request)

    assert item.status == RequestItemStatus.BRAK
    assert not Document.objects.filter(pk=document.pk).exists()


@pytest.mark.django_db
def test_guest_delete_denied_for_different_session(request_item):
    upload_request = _django_request()
    upload_request.session.save()
    document = UploadDocumentService.upload_for_item(
        request_item, make_pdf_upload(), django_request=upload_request
    )

    other_request = _django_request()
    other_request.session.save()

    with pytest.raises(PermissionDeniedAppError):
        GuestDeleteService.delete_own_upload(document.pk, other_request)


@pytest.mark.django_db
def test_guest_delete_denied_after_item_accepted(request_item):
    upload_request = _django_request()
    upload_request.session.save()
    document = UploadDocumentService.upload_for_item(
        request_item, make_pdf_upload(), django_request=upload_request
    )
    DocumentReviewService.accept(request_item)

    with pytest.raises(ValidationAppError):
        GuestDeleteService.delete_own_upload(document.pk, upload_request)
