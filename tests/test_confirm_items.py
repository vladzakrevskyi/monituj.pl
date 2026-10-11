"""Items without a file ("Bez pliku"): something for the client to do and
confirm - "Nadaj biuru uprawnienia w KSeF". The client clicks "Zrobione";
from there it is an ordinary delivered item the sender accepts or sends
back."""

import pytest
from django.urls import reverse

from apps.documents.services import (
    ConfirmationService,
    DocumentReviewService,
    UploadDocumentService,
)
from apps.notifications.inbox import send_pending_upload_emails
from apps.notifications.models import Notification, NotificationKind
from apps.requests import item_kinds, request_templates, template_library
from apps.requests.models import RequestItem, RequestItemKind, RequestItemStatus
from apps.requests.services import RequestService
from tests.conftest import make_pdf_upload, page_text

KSEF = "Nadaj biuru uprawnienia w KSeF"


@pytest.fixture
def confirm_item(request_record):
    return RequestItem.objects.create(
        request=request_record, name=KSEF, kind=RequestItemKind.CONFIRM
    )


def _url(request_record, item):
    return f"/api/public/{request_record.public_token}/items/{item.pk}/confirm/"


def _open(client, request_record):
    return client.get(f"/d/{request_record.public_token}/")


def _plain(text):
    return text.replace("\u00a0", " ")


# --- the name carries the kind through forms, templates and schedules ---------


def test_a_name_ending_bez_pliku_is_a_confirm_item():
    assert item_kinds.split(f"{KSEF} (bez pliku)") == (KSEF, True)
    assert item_kinds.split(f"{KSEF} (Bez Pliku) ") == (KSEF, True)
    assert item_kinds.split("Wyciąg bankowy") == ("Wyciąg bankowy", False)
    assert item_kinds.split("(bez pliku)") == ("(bez pliku)", False)
    assert item_kinds.split(item_kinds.joined(KSEF, True)) == (KSEF, True)


@pytest.mark.django_db
def test_request_is_made_with_both_kinds(user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Start współpracy",
        description="",
        deadline=None,
        item_names=["Umowa", f"{KSEF} (bez pliku)"],
    )

    kinds = dict(request_obj.items.values_list("name", "kind"))
    assert kinds == {"Umowa": RequestItemKind.FILE, KSEF: RequestItemKind.CONFIRM}


@pytest.mark.django_db
def test_form_posts_the_kind_and_a_template_keeps_it(client, user, client_record):
    client.force_login(user)

    response = client.post(
        reverse("requests:create"),
        {
            "clients": [client_record.pk],
            "name": "Start współpracy",
            "items": ["Umowa", f"{KSEF} (bez pliku)"],
            "deadline_choice": "14",
            "reminder_preset": "standard",
            "retention_choice": "90",
        },
    )

    assert response.status_code == 302, page_text(response)[:400]
    request_obj = user.requests.get()
    assert request_obj.items.get(name=KSEF).is_confirm
    template = request_templates.from_request(user, request_obj)
    assert template.item_names == ["Umowa", f"{KSEF} (bez pliku)"]


def test_ready_template_for_a_new_client_has_the_ksef_item_without_a_file():
    ready = template_library.get("nowy-klient-biura-rachunkowego")

    assert ready.confirm
    assert all(name in dict(ready.items) for name in ready.confirm)
    assert "Nadanie biuru uprawnień w KSeF (bez pliku)" in ready.item_names


@pytest.mark.django_db
def test_ready_template_page_marks_the_item(client):
    page = _plain(
        client.get("/szablony/nowy-klient-biura-rachunkowego/").content.decode()
    )

    assert 'Nadanie biuru uprawnień w KSeF <span class="item-kind">bez pliku' in page


# --- the client's side -------------------------------------------------------------


@pytest.mark.django_db
def test_page_shows_a_button_instead_of_an_upload(client, request_record, confirm_item):
    page = _plain(_open(client, request_record).content.decode())

    block = page[page.index(f'data-item-id="{confirm_item.pk}"') :]
    assert "data-confirm-done" in block
    assert "upload-input" not in block  # the only other item is above it
    assert "Do zrobienia" in block and "To mnie nie dotyczy" in block


@pytest.mark.django_db
def test_client_confirms_and_the_sender_hears(
    client, request_record, request_item, confirm_item, mailoutbox
):
    _open(client, request_record)

    response = client.post(_url(request_record, confirm_item))

    assert response.status_code == 200
    assert response.json()["data"]["item"]["status"] == {
        "code": "dostarczony",
        "label": "Potwierdzone",
    }
    confirm_item.refresh_from_db()
    assert confirm_item.status == RequestItemStatus.DOSTARCZONY
    notice = Notification.objects.get(kind=NotificationKind.CONFIRMED)
    assert notice.item == confirm_item
    assert send_pending_upload_emails(now=notice.created_at.replace(year=2100)) == 1
    email = mailoutbox[-1]
    assert email.subject.startswith("Klient potwierdził wykonanie")
    assert "zrobione (bez pliku)" in _plain(email.body)
    page = _plain(_open(client, request_record).content.decode())
    assert "Potwierdzone przez Ciebie" in page and "data-confirm-undo" in page


@pytest.mark.django_db
def test_twice_is_one_notice_and_undo_takes_it_back(
    client, request_record, confirm_item
):
    _open(client, request_record)
    url = _url(request_record, confirm_item)

    assert client.post(url).status_code == 200
    assert client.post(url).status_code == 400  # already confirmed
    assert client.delete(url).status_code == 200

    confirm_item.refresh_from_db()
    assert confirm_item.status == RequestItemStatus.BRAK
    assert not Notification.objects.exists()
    assert client.post(url).status_code == 200
    assert Notification.objects.count() == 1


@pytest.mark.django_db
def test_only_through_the_opened_link_and_not_after_closing(
    client, request_record, confirm_item
):
    url = _url(request_record, confirm_item)

    assert client.post(url).status_code == 403  # the link wasn't opened here
    _open(client, request_record)
    RequestService.close(request_record, actor=request_record.created_by)
    assert client.post(url).status_code == 400
    confirm_item.refresh_from_db()
    assert confirm_item.status == RequestItemStatus.BRAK


@pytest.mark.django_db
def test_no_file_for_it_and_no_button_for_a_file_item(
    client, request_record, request_item, confirm_item
):
    from apps.common.exceptions import ValidationAppError

    with pytest.raises(ValidationAppError):
        UploadDocumentService.upload_for_item(confirm_item, make_pdf_upload())
    _open(client, request_record)
    assert client.post(_url(request_record, request_item)).status_code == 400


@pytest.mark.django_db
def test_not_applicable_works_for_it_too(client, request_record, confirm_item):
    import json

    _open(client, request_record)

    response = client.post(
        f"/api/public/{request_record.public_token}/items/{confirm_item.pk}"
        "/not-applicable/",
        json.dumps({"reason": "Biuro ma już uprawnienia"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    confirm_item.refresh_from_db()
    assert confirm_item.status == RequestItemStatus.NIE_DOTYCZY


# --- the sender's side -------------------------------------------------------------


@pytest.mark.django_db
def test_sender_accepts_or_sends_it_back(
    client, user, request_record, confirm_item, mailoutbox
):
    ConfirmationService.confirm(confirm_item)
    client.force_login(user)

    page = client.get(reverse("requests:detail", args=[request_record.pk]))
    text = _plain(page.content.decode())
    assert '<span class="item-kind"' in text and "klient potwierdza" in text
    assert "Potwierdzone" in text

    DocumentReviewService.reject(confirm_item, "W KSeF nie widać uprawnień")
    confirm_item.refresh_from_db()
    assert confirm_item.status == RequestItemStatus.ODRZUCONY
    body = _plain(mailoutbox[-1].body)
    assert "W KSeF nie widać uprawnień" in body
    assert "potwierdź tutaj" in body and "Prześlij poprawiony" not in body
    # The client does it and confirms again; this time it is accepted.
    ConfirmationService.confirm(confirm_item)
    DocumentReviewService.accept(confirm_item)
    confirm_item.refresh_from_db()
    assert confirm_item.status == RequestItemStatus.ZAAKCEPTOWANY


@pytest.mark.django_db
def test_confirmed_item_counts_as_delivered_and_stops_reminders(
    request_record, request_item, confirm_item
):
    from apps.requests.services import compute_status, with_stats

    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    ConfirmationService.confirm(confirm_item)

    annotated = with_stats(type(request_record).objects.filter(pk=request_record.pk))
    assert compute_status(annotated.get()).value == "kompletny"
