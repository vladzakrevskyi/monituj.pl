from datetime import timedelta

import pytest
from django.core import mail
from django.test import Client as BrowserClient
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.documents.services import GuestDeleteService, UploadDocumentService
from apps.notifications import inbox
from apps.notifications.models import EmailLog, EmailTemplate, Notification
from apps.requests.models import RequestItem
from tests.conftest import make_pdf_upload, make_png_upload, page_text


def _later(minutes):
    return timezone.now() + timedelta(minutes=minutes)


def _owner_emails(user):
    return [m for m in mail.outbox if m.to == [user.email]]


@pytest.fixture
def second_item(request_record):
    return RequestItem.objects.create(request=request_record, name="Wyciąg bankowy")


@pytest.fixture
def third_item(request_record):
    # Keeps the request incomplete, so no "komplet" email gets in the way.
    return RequestItem.objects.create(request=request_record, name="Raport kasowy")


@pytest.mark.django_db
def test_every_upload_leaves_a_notice_for_the_sender(user, request_item):
    document = UploadDocumentService.upload_for_item(request_item, make_pdf_upload())

    notice = Notification.objects.get()
    assert notice.user == user
    assert notice.document == document
    assert notice.read_at is None
    assert inbox.unread_count(user) == 1


@pytest.mark.django_db
def test_email_waits_until_the_recipient_stops_uploading(
    user, request_item, second_item, third_item
):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload("a.pdf"))
    UploadDocumentService.upload_for_item(second_item, make_png_upload("b.png"))
    mail.outbox.clear()

    assert inbox.send_pending_upload_emails(now=timezone.now()) == 0
    assert _owner_emails(user) == []

    assert inbox.send_pending_upload_emails(now=_later(2)) == 1
    [email] = _owner_emails(user)
    assert email.subject == "Nowe dokumenty (2): Dokumenty za wrzesien – Monituj"
    body = email.body.replace(" ", " ")
    # One file per line, even after the typography pass.
    assert "\n- Faktury sprzedaży: a.pdf\n- Wyciąg bankowy: b.png\n" in body
    assert "Acme Sp. z o.o." in body
    assert "Dostarczono: 2 z 3" in body
    assert "Raport kasowy" in body
    # Sent once only.
    assert inbox.send_pending_upload_emails(now=_later(5)) == 0


@pytest.mark.django_db
def test_single_upload_email(user, request_item, second_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    mail.outbox.clear()

    inbox.send_pending_upload_emails(now=_later(2))

    [email] = _owner_emails(user)
    assert email.subject.startswith("Nowy dokument: ")
    assert "/przypomnienia/" in email.body


@pytest.mark.django_db
def test_non_stop_uploading_still_gets_an_email(
    user, request_item, second_item, third_item
):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    Notification.objects.update(created_at=timezone.now() - timedelta(minutes=11))
    UploadDocumentService.upload_for_item(second_item, make_png_upload())
    mail.outbox.clear()

    assert inbox.send_pending_upload_emails(now=timezone.now()) == 1


@pytest.mark.django_db
def test_no_email_for_what_the_sender_already_saw(user, request_item, second_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    inbox.mark_read(user)
    mail.outbox.clear()

    inbox.send_pending_upload_emails(now=_later(2))

    assert _owner_emails(user) == []
    assert Notification.objects.get().emailed_at is not None


@pytest.mark.django_db
def test_complete_request_sends_only_the_complete_email(user, request_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())

    inbox.send_pending_upload_emails(now=_later(2))

    templates = set(
        EmailLog.objects.filter(recipient_email=user.email).values_list(
            "template", flat=True
        )
    )
    assert templates == {EmailTemplate.COMPLETE_OWNER}


@pytest.mark.django_db
def test_deleted_upload_leaves_no_notice(user, request_item, second_item, rf):
    from django.contrib.sessions.backends.db import SessionStore

    django_request = rf.post("/")
    django_request.session = SessionStore()
    document = UploadDocumentService.upload_for_item(
        request_item, make_pdf_upload(), django_request=django_request
    )

    GuestDeleteService.delete_own_upload(document.pk, django_request)

    assert not Notification.objects.exists()


@pytest.mark.django_db
def test_notices_page_lists_and_marks_them_read(client, user, request_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload("umowa.pdf"))
    client.force_login(user)

    panel = page_text(client.get(reverse("accounts:panel")))
    page = page_text(client.get(reverse("notifications:list")))

    assert 'title="Nowe dokumenty od klientów">1</span>' in panel
    assert "umowa.pdf" in page
    assert "Faktury sprzedaży" in page
    assert "is-unread" in page
    assert inbox.unread_count(user) == 0
    assert "is-unread" not in page_text(client.get(reverse("notifications:list")))


@pytest.mark.django_db
def test_opening_the_request_marks_its_notices_read(client, user, request_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    client.force_login(user)

    client.get(reverse("requests:detail", args=[request_item.request_id]))

    assert inbox.unread_count(user) == 0


@pytest.mark.django_db
def test_nobody_else_sees_the_notices(request_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload("tajne.pdf"))
    stranger = User.objects.create_user(email="obcy@example.com", password="x-pass-1!")
    browser = BrowserClient()
    browser.force_login(stranger)

    page = browser.get(reverse("notifications:list")).content.decode()

    assert "tajne.pdf" not in page
    assert inbox.unread_count(stranger) == 0


@pytest.mark.django_db
def test_notices_page_needs_login_and_is_never_indexed(client):
    response = client.get(reverse("notifications:list"))

    assert response.status_code == 302
    assert response["X-Robots-Tag"] == "noindex, nofollow"
