import pytest
from django.core import mail
from django.test import Client as Browser
from django.urls import reverse

from apps.documents.services import DocumentReviewService
from apps.requests import recipient_files
from apps.requests.models import Request, RequestItem
from tests.conftest import make_pdf_upload, page_text


def _page(browser, request_obj):
    return browser.get(
        reverse("public:request-detail", args=[request_obj.public_token])
    )


def _upload(browser, item, name="faktura.pdf"):
    _page(browser, item.request)
    response = browser.post(
        reverse("documents_api:upload", args=[item.request.public_token, item.pk]),
        {"file": make_pdf_upload(name)},
    )
    return response.json()["data"]["document"]["id"]


def _ask_for_link(browser, request_obj):
    return browser.post(
        reverse("public:recipient-files", args=[request_obj.public_token])
    )


def _mailed_link(to):
    body = next(m for m in reversed(mail.outbox) if m.to == [to]).body
    return next(w for w in body.split() if "/moje-pliki/" in w)


@pytest.fixture
def second_item(request_record):
    return RequestItem.objects.create(request=request_record, name="Wyciąg")


@pytest.mark.django_db
def test_accepted_document_stays_visible_and_downloadable(
    client, request_item, second_item
):
    document_id = _upload(client, request_item)
    request_item.refresh_from_db()
    DocumentReviewService.accept(request_item)

    html = page_text(_page(client, request_item.request))
    download = reverse("documents_api:download", args=[document_id])

    assert "Dokument zaakceptowany." in html
    assert "faktura.pdf" in html
    assert f'href="{download}"' in html
    assert client.get(download).status_code == 200
    # Accepted: no deleting it and no new uploads for that item.
    block = html[html.index(f'data-item-id="{request_item.pk}"') :]
    block = block[: block.index('class="request-item"', 10)]
    assert "delete-document" not in block
    assert "upload-zone" not in block


@pytest.mark.django_db
def test_other_device_gets_the_files_after_a_mailed_link(client, request_item):
    document_id = _upload(client, request_item)
    phone = Browser()

    html = page_text(_page(phone, request_item.request))
    assert "faktura.pdf" not in html
    assert "Nie widzisz swoich plików?" in html

    mail.outbox.clear()
    _ask_for_link(phone, request_item.request)
    link = _mailed_link(request_item.request.client.email)

    # Opening the link shows a button only; the click grants access.
    assert phone.get(link).status_code == 200
    assert "faktura.pdf" not in page_text(_page(phone, request_item.request))
    phone.post(link)

    html = page_text(_page(phone, request_item.request))
    assert "faktura.pdf" in html
    assert "Nie widzisz swoich plików?" not in html
    assert (
        phone.get(reverse("documents_api:download", args=[document_id])).status_code
        == 200
    )


@pytest.mark.django_db
def test_note_shows_only_when_files_are_hidden(client, request_item):
    empty = page_text(_page(Browser(), request_item.request))
    _upload(client, request_item)

    assert "Nie widzisz swoich plików?" not in empty
    # The uploader sees their file; someone else with the link sees the note.
    assert "Nie widzisz swoich plików?" not in page_text(
        _page(client, request_item.request)
    )
    assert "Nie widzisz swoich plików?" in page_text(
        _page(Browser(), request_item.request)
    )


@pytest.mark.django_db
def test_link_goes_only_to_the_requests_own_address(client, request_item):
    _upload(client, request_item)
    mail.outbox.clear()

    stranger = Browser()
    _page(stranger, request_item.request)
    stranger.post(
        reverse("public:recipient-files", args=[request_item.request.public_token]),
        {"email": "attacker@example.com"},
    )

    assert {m.to[0] for m in mail.outbox} == {request_item.request.client.email}


@pytest.mark.django_db
def test_asking_needs_the_request_opened_first(request_item):
    mail.outbox.clear()

    Browser().post(
        reverse("public:recipient-files", args=[request_item.request.public_token])
    )

    assert mail.outbox == []


@pytest.mark.django_db
def test_link_is_rate_limited_quietly(client, request_item):
    _upload(client, request_item)
    browser = Browser()
    _page(browser, request_item.request)
    mail.outbox.clear()

    for _ in range(recipient_files.LINKS_PER_REQUEST_HOUR + 2):
        _ask_for_link(browser, request_item.request)

    assert len(mail.outbox) == recipient_files.LINKS_PER_REQUEST_HOUR


@pytest.mark.django_db
def test_link_works_only_for_its_own_request(client, request_item, user, client_record):
    _upload(client, request_item)
    other = Request.objects.create(client=client_record, created_by=user, name="Inna")
    mail.outbox.clear()
    browser = Browser()
    _page(browser, request_item.request)
    _ask_for_link(browser, request_item.request)
    link = _mailed_link(request_item.request.client.email)
    signed = link.rstrip("/").rsplit("/", 1)[1]

    response = browser.post(
        reverse("public:recipient-files-confirm", args=[other.public_token, signed])
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_link_dies_when_the_recipient_address_changes(client, request_item):
    _upload(client, request_item)
    browser = Browser()
    _page(browser, request_item.request)
    mail.outbox.clear()
    _ask_for_link(browser, request_item.request)
    link = _mailed_link(request_item.request.client.email)
    client_record = request_item.request.client
    client_record.email = "nowy@example.com"
    client_record.save()

    assert browser.post(link).status_code == 400


@pytest.mark.django_db
def test_expired_link_is_refused(client, request_item, monkeypatch):
    _upload(client, request_item)
    browser = Browser()
    _page(browser, request_item.request)
    mail.outbox.clear()
    _ask_for_link(browser, request_item.request)
    link = _mailed_link(request_item.request.client.email)
    monkeypatch.setattr(recipient_files, "LINK_MAX_AGE", -1)

    assert browser.post(link).status_code == 400


@pytest.mark.django_db
def test_mailbox_proof_also_opens_a_password_protected_request(user, client_record):
    from django.contrib.auth.hashers import make_password

    from apps.requests.models import PasswordProtectedAccess

    request_obj = Request.objects.create(
        client=client_record, created_by=user, name="Z hasłem"
    )
    RequestItem.objects.create(request=request_obj, name="Aneks XYZ-17")
    PasswordProtectedAccess.objects.create(
        request=request_obj, password_hash=make_password("Tajne-haslo-1")
    )
    assert "Aneks XYZ-17" not in page_text(_page(Browser(), request_obj))
    browser = Browser()
    signed = recipient_files.signing.dumps(
        {"r": request_obj.pk, "e": client_record.email.lower()},
        salt=recipient_files.SALT,
    )

    browser.post(
        reverse(
            "public:recipient-files-confirm", args=[request_obj.public_token, signed]
        )
    )

    assert "Aneks XYZ-17" in page_text(_page(browser, request_obj))
