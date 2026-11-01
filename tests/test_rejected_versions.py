"""A document sent back and sent again: the rejected file is shown apart
(after the new one, marked "odrzucony"), accepting takes only the new one,
and the ZIP keeps the old one in "Odrzucone/"."""

import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.documents.models import Document, DocumentStatus
from apps.documents.services import DocumentReviewService, UploadDocumentService
from apps.requests.models import Request, RequestItem
from tests.conftest import MINIMAL_PDF_BYTES, page_text


def _pdf(name, extra=b""):
    return SimpleUploadedFile(name, MINIMAL_PDF_BYTES + extra, "application/pdf")


@pytest.fixture
def sent_again(user, client_record):
    """The client sent a statement, it was rejected, then a new one came."""
    request_obj = Request.objects.create(
        client=client_record, created_by=user, name="Dokumenty za październik"
    )
    item = RequestItem.objects.create(request=request_obj, name="Wyciąg bankowy")
    UploadDocumentService.upload_for_item(item, _pdf("wyciag_wrzesien.pdf"))
    DocumentReviewService.reject(item, "To wyciąg za wrzesień")
    item.refresh_from_db()
    UploadDocumentService.upload_for_item(item, _pdf("wyciag_pazdziernik.pdf", b"%2"))
    item.refresh_from_db()
    return request_obj, item


@pytest.mark.django_db
def test_the_rejected_file_comes_after_the_new_one_and_is_marked(
    client, user, sent_again
):
    request_obj, _ = sent_again
    client.force_login(user)

    html = page_text(client.get(reverse("requests:detail", args=[request_obj.pk])))

    new = html.index("wyciag_pazdziernik.pdf")
    old = html.index("wyciag_wrzesien.pdf")
    assert new < old
    assert 'class="file-link--rejected"' in html[new : old + 200]
    assert "odrzucony</span>" in html[old:]
    assert 'data-document-status="uploaded"' in html


@pytest.mark.django_db
def test_accepting_takes_only_the_new_file(sent_again):
    _, item = sent_again

    DocumentReviewService.accept(item)

    statuses = dict(item.documents.values_list("original_filename", "status"))
    assert statuses == {
        "wyciag_pazdziernik.pdf": DocumentStatus.ACCEPTED,
        "wyciag_wrzesien.pdf": DocumentStatus.REJECTED,
    }


@pytest.mark.django_db
def test_the_zip_keeps_rejected_files_apart(client, user, sent_again):
    request_obj, _ = sent_again
    client.force_login(user)

    response = client.get(reverse("requests:files-zip", args=[request_obj.pk]))
    archive = zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content)))

    assert sorted(archive.namelist()) == [
        "01 Wyciąg bankowy/Odrzucone/wyciag_wrzesien.pdf",
        "01 Wyciąg bankowy/wyciag_pazdziernik.pdf",
    ]


@pytest.mark.django_db
def test_the_client_documents_page_shows_the_rejected_file_apart(
    client, user, sent_again
):
    request_obj, _ = sent_again
    client.force_login(user)

    html = page_text(
        client.get(reverse("clients:documents", args=[request_obj.client_id]))
    )

    assert html.index("wyciag_pazdziernik.pdf") < html.index("wyciag_wrzesien.pdf")
    assert "odrzucony</span>" in html


@pytest.mark.django_db
def test_the_client_sees_which_of_their_files_was_rejected(client, sent_again):
    request_obj, item = sent_again
    # The client's own browser: their uploads carry its session.
    session = client.session
    session.save()
    Document.objects.filter(request_item=item).update(
        uploaded_by_session_key=session.session_key
    )

    html = page_text(
        client.get(reverse("public:request-detail", args=[request_obj.public_token]))
    )

    new = html.index("wyciag_pazdziernik.pdf")
    old = html.index("wyciag_wrzesien.pdf")
    assert new < old
    assert "uploaded-file--rejected" in html[new:]
    assert "<strong>odrzucony</strong>" in html[old:]
