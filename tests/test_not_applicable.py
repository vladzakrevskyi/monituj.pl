""" "Nie mam tego dokumentu": the recipient marks a document they don't have
- none this period, or not theirs to give. Reminders about it stop, a
request with nothing else missing is complete; the sender accepts it or
asks for the document after all. And the "Zobacz Monituj" line on a
finished request page."""

import json

import pytest
from django.urls import reverse

from apps.notifications.inbox import send_pending_upload_emails
from apps.notifications.models import Notification, NotificationKind
from apps.requests.models import RequestItem, RequestItemStatus
from apps.requests.services import in_progress
from tests.conftest import make_pdf_upload, page_text

JSON = "application/json"


def _plain(text):
    return text.replace("\u00a0", " ")


def _url(request_record, item):
    return f"/api/public/{request_record.public_token}/items/{item.pk}/not-applicable/"


def _open(client, request_record):
    client.get(f"/d/{request_record.public_token}/")


def _mark(client, request_record, item, reason="W tym okresie go nie było"):
    return client.post(
        _url(request_record, item), json.dumps({"reason": reason}), content_type=JSON
    )


@pytest.fixture
def second_item(request_record):
    return RequestItem.objects.create(request=request_record, name="Faktury kosztowe")


@pytest.mark.django_db
def test_recipient_marks_a_document_they_dont_have(
    client, request_record, request_item, second_item, mailoutbox
):
    _open(client, request_record)

    response = _mark(client, request_record, second_item)

    assert response.status_code == 200
    second_item.refresh_from_db()
    assert second_item.status == RequestItemStatus.NIE_DOTYCZY
    assert second_item.not_applicable_reason == "W tym okresie go nie było"
    assert not second_item.not_applicable_accepted
    # The sender hears about it - in the panel, then in the batched email.
    notice = Notification.objects.get(kind=NotificationKind.NOT_APPLICABLE)
    assert notice.item == second_item
    assert send_pending_upload_emails(now=notice.created_at.replace(year=2100)) == 1
    email = mailoutbox[-1]
    assert email.subject.startswith("Klient nie ma dokumentu")
    assert "nie dotyczy (W tym okresie go nie było)" in _plain(email.body)
    # Still waiting for the other one.
    assert in_progress(request_record.created_by).count() == 1


@pytest.mark.django_db
def test_the_last_one_completes_the_request(
    client, request_record, request_item, mailoutbox
):
    _open(client, request_record)

    _mark(client, request_record, request_item, "Ten dokument mnie nie dotyczy")

    assert in_progress(request_record.created_by).count() == 0
    assert any("Komplet" in m.subject for m in mailoutbox)
    page = page_text(client.get(f"/d/{request_record.public_token}/"))
    assert "Nie masz tego dokumentu: <strong>Ten dokument mnie nie dotyczy" in page
    assert "Zobacz, jak to działa" in page


@pytest.mark.django_db
def test_a_reason_is_needed_and_only_for_a_missing_document(
    client, request_record, request_item
):
    _open(client, request_record)

    assert _mark(client, request_record, request_item, "  ").status_code == 400
    client.post(
        f"/api/public/{request_record.public_token}/items/{request_item.pk}/upload/",
        {"file": make_pdf_upload()},
    )
    assert _mark(client, request_record, request_item).status_code == 400


@pytest.mark.django_db
def test_without_access_nothing_changes(client, request_record, request_item):
    from apps.requests.models import PasswordProtectedAccess

    PasswordProtectedAccess.objects.create(request=request_record, password_hash="x")

    response = _mark(client, request_record, request_item)

    assert response.status_code == 403
    request_item.refresh_from_db()
    assert request_item.status == RequestItemStatus.BRAK


@pytest.mark.django_db
def test_undo_until_the_sender_accepts(client, request_record, request_item):
    _open(client, request_record)
    _mark(client, request_record, request_item)

    client.delete(_url(request_record, request_item))
    request_item.refresh_from_db()
    assert request_item.status == RequestItemStatus.BRAK

    _mark(client, request_record, request_item)
    RequestItem.objects.filter(pk=request_item.pk).update(not_applicable_accepted=True)
    assert client.delete(_url(request_record, request_item)).status_code == 400


@pytest.mark.django_db
def test_sender_accepts_or_asks_after_all(
    client, user, request_record, request_item, second_item, mailoutbox
):
    browser = client
    _open(browser, request_record)
    _mark(browser, request_record, request_item)
    _mark(browser, request_record, second_item)
    browser.force_login(user)
    base = f"/api/requests/{request_record.pk}/items"

    browser.post(f"{base}/{request_item.pk}/accept/")
    browser.post(
        f"{base}/{second_item.pk}/reject/",
        json.dumps({"reason": "Potrzebuję go do VAT"}),
        content_type=JSON,
    )

    request_item.refresh_from_db()
    second_item.refresh_from_db()
    assert request_item.status == RequestItemStatus.NIE_DOTYCZY
    assert request_item.not_applicable_accepted
    # Back to missing, with the sender's reason - reminders about it resume.
    assert second_item.status == RequestItemStatus.ODRZUCONY
    assert second_item.rejection_reason == "Potrzebuję go do VAT"
    assert second_item.not_applicable_reason == ""
    email = mailoutbox[-1]
    assert email.to == [request_record.client.email]
    assert email.subject.startswith("Nadawca prosi jednak o dokument")
    assert "Potrzebuję go do VAT" in _plain(email.body)


@pytest.mark.django_db
def test_sender_marks_it_themselves(client, user, request_record, request_item):
    client.force_login(user)

    client.post(
        reverse(
            "documents_api:not-applicable-item",
            args=[request_record.pk, request_item.pk],
        ),
        json.dumps({"reason": ""}),
        content_type=JSON,
    )

    request_item.refresh_from_db()
    assert request_item.status == RequestItemStatus.NIE_DOTYCZY
    assert request_item.not_applicable_accepted
    page = page_text(client.get(reverse("requests:detail", args=[request_record.pk])))
    assert "Oznaczone przez Ciebie" in page


@pytest.mark.django_db
def test_uploading_a_file_after_all_makes_it_delivered(
    client, request_record, request_item
):
    _open(client, request_record)
    _mark(client, request_record, request_item)
    client.delete(_url(request_record, request_item))

    client.post(
        f"/api/public/{request_record.public_token}/items/{request_item.pk}/upload/",
        {"file": make_pdf_upload()},
    )

    request_item.refresh_from_db()
    assert request_item.status == RequestItemStatus.DOSTARCZONY
    assert request_item.not_applicable_reason == ""


@pytest.mark.django_db
def test_reminders_skip_it(client, request_record, request_item, second_item):
    from apps.notifications.services import NOT_DELIVERED

    _open(client, request_record)
    _mark(client, request_record, second_item)

    missing = list(
        request_record.items.filter(status__in=NOT_DELIVERED).values_list(
            "name", flat=True
        )
    )
    assert missing == [request_item.name]


@pytest.mark.django_db
def test_monituj_line_only_once_everything_is_there(
    client, request_record, request_item
):
    page = page_text(client.get(f"/d/{request_record.public_token}/"))

    # In the page but hidden until the request is complete.
    assert "data-done hidden" in page
    # A plain link: nothing about the recipient in it.
    assert "?utm_source=prosba&amp;utm_medium=strona_odbiorcy" in page
    assert (
        request_record.public_token not in page.split("Zobacz, jak to działa")[0][-200:]
    )


@pytest.mark.django_db
def test_toggling_doesnt_flood_the_sender(client, request_record, request_item):
    _open(client, request_record)

    for _ in range(10):
        _mark(client, request_record, request_item)
        client.delete(_url(request_record, request_item))
    _mark(client, request_record, request_item)

    assert (
        Notification.objects.filter(kind=NotificationKind.NOT_APPLICABLE).count() == 1
    )


@pytest.mark.django_db
def test_answers_are_limited_per_hour(client, request_record, request_item, settings):
    from apps.documents import api

    _open(client, request_record)
    api.NOT_APPLICABLE_PER_IP_HOUR, before = 3, api.NOT_APPLICABLE_PER_IP_HOUR
    try:
        for _ in range(3):
            client.delete(_url(request_record, request_item))
        response = _mark(client, request_record, request_item)
    finally:
        api.NOT_APPLICABLE_PER_IP_HOUR = before

    assert response.status_code == 429
