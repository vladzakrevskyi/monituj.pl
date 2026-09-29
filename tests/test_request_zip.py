import io
import zipfile
from urllib.parse import unquote

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.audit.models import AuditEvent, AuditLog
from apps.documents.archive import safe_name
from apps.documents.services import UploadDocumentService
from apps.requests.models import Request, RequestItem
from tests.conftest import MINIMAL_PDF_BYTES, make_pdf_upload, make_png_upload


@pytest.fixture
def request_with_files(user, client_record):
    request_obj = Request.objects.create(
        client=client_record, created_by=user, name="Dokumenty za wrzesień"
    )
    sales = RequestItem.objects.create(request=request_obj, name="Faktury sprzedaży")
    costs = RequestItem.objects.create(request=request_obj, name="Faktury/koszty")
    RequestItem.objects.create(request=request_obj, name="Wyciąg bankowy")
    UploadDocumentService.upload_for_item(sales, make_pdf_upload("faktura.pdf"))
    # Another file with the same name.
    UploadDocumentService.upload_for_item(
        sales,
        SimpleUploadedFile(
            "faktura.pdf", MINIMAL_PDF_BYTES + b"\n% druga", "application/pdf"
        ),
    )
    UploadDocumentService.upload_for_item(costs, make_png_upload("paragon.png"))
    return request_obj


def _zip(response):
    return zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content)))


@pytest.mark.django_db
def test_owner_downloads_every_file_in_folders(client, user, request_with_files):
    client.force_login(user)

    response = client.get(reverse("requests:files-zip", args=[request_with_files.pk]))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"
    assert "Dokumenty za wrzesień.zip" in unquote(response["Content-Disposition"])
    archive = _zip(response)
    assert sorted(archive.namelist()) == [
        "01 Faktury sprzedaży/faktura (2).pdf",
        "01 Faktury sprzedaży/faktura.pdf",
        "02 Faktury koszty/paragon.png",
    ]
    # Decrypted - the real files, not what is stored on disk.
    assert archive.read("01 Faktury sprzedaży/faktura.pdf").startswith(b"%PDF")
    assert (
        AuditLog.objects.filter(
            event=AuditEvent.FILE_DOWNLOAD, metadata__zip=True
        ).count()
        == 3
    )


@pytest.mark.django_db
def test_button_shows_only_when_there_are_files(client, user, request_record):
    client.force_login(user)
    url = reverse("requests:files-zip", args=[request_record.pk])

    page = client.get(reverse("requests:detail", args=[request_record.pk]))
    response = client.get(url)

    assert url not in page.content.decode()
    assert response.status_code == 302


@pytest.mark.django_db
def test_someone_elses_request_is_not_found(client, request_with_files):
    from apps.accounts.models import User

    stranger = User.objects.create_user(email="obcy@example.com", password="x-pass-1!")
    client.force_login(stranger)

    response = client.get(reverse("requests:files-zip", args=[request_with_files.pk]))

    assert response.status_code == 404


def test_names_are_safe_on_every_system():
    assert safe_name('Faktury: "koszty" 09/2026') == "Faktury koszty 09 2026"
    assert safe_name("  ..  ") == "plik"
