import re
from datetime import timedelta

import pytest
from django.core import mail
from django.test import Client as FreshClient
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccountToken, AccountTokenPurpose, User
from apps.audit.models import AuditLog
from apps.clients.models import Client
from apps.documents.models import Document
from apps.documents.services import UploadDocumentService
from apps.documents.storage import private_storage
from apps.notifications.models import EmailLog, EmailTemplate
from apps.reminders.tasks import send_automatic_reminders
from apps.requests.models import Request, RequestItem, RequestItemStatus
from tests.conftest import make_pdf_upload, page_text

PASSWORD = "Sup3r-Secret-Pass!23"


@pytest.fixture
def owner(db):
    return User.objects.create_user(
        email="biuro@example.com", password=PASSWORD, display_name="Biuro Nowak"
    )


@pytest.fixture
def owner_data(owner):
    """One open request with an uploaded file and one finished request."""
    client_obj = Client.objects.create(
        owner=owner, name="Kowalski", email="kowalski@example.com"
    )
    open_request = Request.objects.create(
        client=client_obj, created_by=owner, name="Dokumenty za wrzesień"
    )
    uploaded = RequestItem.objects.create(request=open_request, name="Faktury")
    RequestItem.objects.create(request=open_request, name="Wyciąg")
    document = UploadDocumentService.upload_for_item(uploaded, make_pdf_upload())
    done_client = Client.objects.create(
        owner=owner, name="Nowak", email="nowak@example.com"
    )
    done_request = Request.objects.create(
        client=done_client, created_by=owner, name="Umowa"
    )
    RequestItem.objects.create(
        request=done_request, name="Umowa", status=RequestItemStatus.ZAAKCEPTOWANY
    )
    mail.outbox.clear()
    return {"request": open_request, "document": document}


def _ask_for_deletion(client, password=PASSWORD, understood=True):
    data = {"form_action": "delete", "current_password": password}
    if understood:
        data["understood"] = "on"
    return client.post(
        reverse("accounts:settings"), data, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
    )


def _confirm_path():
    body = mail.outbox[-1].body
    return re.search(r"https?://[^/\s]+(/ustawienia/usun-konto/\S+/)", body).group(1)


@pytest.mark.django_db
def test_wrong_password_does_not_start_deletion(client, owner):
    client.force_login(owner)

    response = _ask_for_deletion(client, password="zle-haslo")

    assert response.status_code == 400
    assert "current_password" in response.json()["error"]["fields"]
    assert not AccountToken.objects.filter(
        purpose=AccountTokenPurpose.ACCOUNT_DELETION
    ).exists()
    assert mail.outbox == []


@pytest.mark.django_db
def test_deletion_requires_ticking_the_consequences_box(client, owner):
    client.force_login(owner)

    response = _ask_for_deletion(client, understood=False)

    assert response.status_code == 400
    assert "understood" in response.json()["error"]["fields"]
    assert mail.outbox == []


@pytest.mark.django_db
def test_request_mails_a_confirmation_link_and_keeps_the_account(
    client, owner, owner_data
):
    client.force_login(owner)

    response = _ask_for_deletion(client)

    assert response.status_code == 200
    assert User.objects.filter(pk=owner.pk).exists()
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [owner.email]
    assert "/ustawienia/usun-konto/potwierdz/" in mail.outbox[0].body


@pytest.mark.django_db
def test_opening_the_link_only_shows_a_summary(client, owner, owner_data):
    client.force_login(owner)
    _ask_for_deletion(client)

    response = FreshClient().get(_confirm_path())

    assert response.status_code == 200
    assert "Usuń konto i wszystkie dane" in page_text(response)
    assert User.objects.filter(pk=owner.pk).exists()


@pytest.mark.django_db
def test_confirming_erases_everything_and_informs_everyone(
    client, owner, owner_data, django_capture_on_commit_callbacks
):
    client.force_login(owner)
    _ask_for_deletion(client)
    path = _confirm_path()
    storage_key = owner_data["document"].storage_key
    other = User.objects.create_user(email="inny@example.com", password=PASSWORD)
    other_client = Client.objects.create(owner=other, name="X", email="x@example.com")
    mail.outbox.clear()

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(path)

    assert "Konto zostało usunięte" in page_text(response)
    assert not User.objects.filter(pk=owner.pk).exists()
    assert not Client.objects.filter(owner_id=owner.pk).exists()
    assert not Request.objects.filter(created_by_id=owner.pk).exists()
    assert not Document.objects.exists()
    assert not private_storage.exists(storage_key)
    assert not AuditLog.objects.filter(metadata__email=owner.email).exists()
    assert not AuditLog.objects.filter(actor_id=owner.pk).exists()
    assert not EmailLog.objects.exists()
    assert Client.objects.filter(pk=other_client.pk).exists()
    # Only the open request's recipient is told; the finished one needs nothing.
    recipients = sorted(message.to[0] for message in mail.outbox)
    assert recipients == ["biuro@example.com", "kowalski@example.com"]
    notice = next(m for m in mail.outbox if m.to == ["kowalski@example.com"])
    assert "Dokumenty za wrzesień" in notice.subject
    assert "trwale usunięte" in notice.body
    assert client.get(reverse("accounts:panel")).status_code == 302


@pytest.mark.django_db
def test_reminders_stop_after_deletion(
    client, owner, owner_data, django_capture_on_commit_callbacks
):
    Request.objects.filter(pk=owner_data["request"].pk).update(
        created_at=timezone.now() - timedelta(days=30)
    )
    client.force_login(owner)
    _ask_for_deletion(client)
    with django_capture_on_commit_callbacks(execute=True):
        client.post(_confirm_path())
    mail.outbox.clear()

    assert send_automatic_reminders() == 0
    assert mail.outbox == []


@pytest.mark.django_db
def test_link_works_only_once(client, owner):
    client.force_login(owner)
    _ask_for_deletion(client)
    path = _confirm_path()
    client.post(path)

    response = FreshClient().post(path)

    assert "Nieprawidłowy link" in page_text(response)


@pytest.mark.django_db
def test_expired_link_deletes_nothing(client, owner):
    client.force_login(owner)
    _ask_for_deletion(client)
    AccountToken.objects.filter(purpose=AccountTokenPurpose.ACCOUNT_DELETION).update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )

    response = client.post(_confirm_path())

    assert "Nieprawidłowy link" in page_text(response)
    assert User.objects.filter(pk=owner.pk).exists()


@pytest.mark.django_db
def test_deletion_emails_leave_no_log(client, owner, owner_data):
    client.force_login(owner)
    _ask_for_deletion(client)

    client.post(_confirm_path())

    assert not EmailLog.objects.filter(
        template__in=[EmailTemplate.ACCOUNT_DELETED, EmailTemplate.REQUEST_CANCELLED]
    ).exists()


@pytest.mark.django_db
def test_demo_account_cannot_request_deletion(client):
    client.post(reverse("demo:start"))

    response = _ask_for_deletion(client)

    assert response.status_code == 403
    assert mail.outbox == []
