import re
from datetime import timedelta

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts.erasure import erase_account
from apps.accounts.models import User
from apps.clients.models import Client
from apps.common.exceptions import ValidationAppError
from apps.documents.services import UploadDocumentService
from apps.reminders.services import ReminderService
from apps.reminders.tasks import send_automatic_reminders
from apps.requests.models import RecipientAccess, Request
from apps.requests.services import RequestService
from tests.conftest import make_pdf_upload, page_text


def _send(owner, recipient_email, name):
    client_obj = Client.objects.create(
        owner=owner, name="Jan Kowalski", email=recipient_email
    )
    return RequestService.create(
        owner=owner,
        client_id=client_obj.pk,
        name=name,
        description="",
        deadline=None,
        item_names=["Faktury"],
    )


def _portal_path(recipient_email):
    message = next(m for m in reversed(mail.outbox) if m.to == [recipient_email])
    return re.search(r"https?://[^\s]+(/moje-prosby/[^\s]+/)", message.body).group(1)


@pytest.fixture
def two_senders(db):
    first = User.objects.create_user(
        email="biuro@example.com", password="x", display_name="Biuro Nowak"
    )
    second = User.objects.create_user(
        email="kadry@example.com", password="x", display_name="Kadry Plus"
    )
    return first, second


@pytest.mark.django_db
def test_recipient_sees_requests_from_every_sender_under_one_link(client, two_senders):
    first, second = two_senders
    _send(first, "jan@example.com", "Dokumenty za wrzesień")
    first_path = _portal_path("jan@example.com")
    _send(second, "JAN@example.com", "Akta pracownika")
    _send(second, "ktos-inny@example.com", "Cudza prośba")

    assert _portal_path("JAN@example.com") == first_path
    content = page_text(client.get(first_path))
    assert "Dokumenty za wrzesień" in content
    assert "Biuro Nowak" in content
    assert "Akta pracownika" in content
    assert "Kadry Plus" in content
    assert "Cudza prośba" not in content


@pytest.mark.django_db
def test_every_recipient_email_carries_the_link(two_senders):
    first, _ = two_senders
    request_obj = _send(first, "jan@example.com", "Dokumenty")
    mail.outbox.clear()

    ReminderService.send_manual(request_obj, actor=first)

    assert "/moje-prosby/" in mail.outbox[0].body


@pytest.mark.django_db
def test_sender_emails_do_not_carry_the_recipient_link(two_senders):
    first, _ = two_senders
    request_obj = _send(first, "jan@example.com", "Dokumenty")
    mail.outbox.clear()

    UploadDocumentService.upload_for_item(request_obj.items.get(), make_pdf_upload())

    to_sender = [m for m in mail.outbox if m.to == [first.email]]
    assert to_sender
    assert all("/moje-prosby/" not in m.body for m in to_sender)


@pytest.mark.django_db
def test_unknown_portal_link_is_not_found(client):
    assert client.get("/moje-prosby/nie-istnieje/").status_code == 404


@pytest.mark.django_db
def test_recipient_link_is_removed_with_the_last_sender(two_senders):
    first, second = two_senders
    _send(first, "jan@example.com", "A")
    _send(second, "jan@example.com", "B")

    erase_account(first)
    assert RecipientAccess.objects.filter(email="jan@example.com").exists()
    erase_account(second)
    assert not RecipientAccess.objects.filter(email="jan@example.com").exists()


@pytest.mark.django_db
def test_closing_stops_uploads_and_reminders(client, two_senders):
    first, _ = two_senders
    request_obj = _send(first, "jan@example.com", "Dokumenty")
    Request.objects.filter(pk=request_obj.pk).update(
        created_at=timezone.now() - timedelta(days=10)
    )
    client.force_login(first)

    client.post(reverse("requests:close", args=[request_obj.pk]))

    request_obj.refresh_from_db()
    assert request_obj.is_closed
    with pytest.raises(ValidationAppError):
        UploadDocumentService.upload_for_item(
            request_obj.items.get(), make_pdf_upload()
        )
    with pytest.raises(ValidationAppError):
        ReminderService.send_manual(request_obj, actor=first)
    assert send_automatic_reminders() == 0
    public = page_text(
        client.get(reverse("public:request-detail", args=[request_obj.public_token]))
    )
    assert "zamknął tę prośbę" in public
    assert "upload-zone" not in public


@pytest.mark.django_db
def test_closed_request_can_be_reopened(client, two_senders):
    first, _ = two_senders
    request_obj = _send(first, "jan@example.com", "Dokumenty")
    client.force_login(first)
    client.post(reverse("requests:close", args=[request_obj.pk]))

    client.post(reverse("requests:close", args=[request_obj.pk]), {"action": "reopen"})

    request_obj.refresh_from_db()
    assert not request_obj.is_closed
    UploadDocumentService.upload_for_item(request_obj.items.get(), make_pdf_upload())


@pytest.mark.django_db
def test_only_the_owner_can_close(client, two_senders):
    first, second = two_senders
    request_obj = _send(first, "jan@example.com", "Dokumenty")
    client.force_login(second)

    response = client.post(reverse("requests:close", args=[request_obj.pk]))

    assert response.status_code == 404
    request_obj.refresh_from_db()
    assert not request_obj.is_closed


@pytest.mark.django_db
def test_closed_requests_have_their_own_filter_tab(client, two_senders):
    first, _ = two_senders
    open_request = _send(first, "jan@example.com", "Otwarta")
    closed = _send(first, "ola@example.com", "Zamknięta prośba")
    RequestService.close(closed, actor=first)
    client.force_login(first)

    content = page_text(client.get(reverse("requests:list") + "?status=zamkniety"))

    assert "Zamknięta prośba" in content
    assert open_request.name not in content
