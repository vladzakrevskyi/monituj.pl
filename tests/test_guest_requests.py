import re
from datetime import timedelta

import pytest
from django.core import mail
from django.test import Client as BrowserClient
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import GuestAccess, User
from apps.clients.models import Client
from apps.documents.services import UploadDocumentService
from apps.reminders.tasks import send_automatic_reminders
from apps.requests.guest import GuestRequestService
from apps.requests.links import guest_panel_url
from apps.requests.models import Request
from apps.requests.services import RequestService
from tests.conftest import make_pdf_upload, page_text

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def _form(**overrides):
    data = {
        "sender_name": "Biuro Nowak",
        "sender_email": "biuro@example.com",
        "client_name": "Jan Kowalski",
        "client_email": "jan@example.com",
        "name": "Dokumenty za wrzesień",
        "description": "",
        "items": ["Faktury", "Wyciąg"],
        "password": "",
        "accept_terms": "on",
    }
    data.update(overrides)
    return data


def _submit(client, ip="10.0.0.1", **overrides):
    return client.post(
        reverse("public:guest-request-create"),
        _form(**overrides),
        REMOTE_ADDR=ip,
        **AJAX,
    )


def _link(message, path_prefix):
    match = re.search(rf"https?://[^\s\"<]+({path_prefix}[^\s\"<]+)", message.body)
    return match.group(1)


def _confirm(client, sender="biuro@example.com"):
    message = next(
        m
        for m in reversed(mail.outbox)
        if m.to == [sender] and "/wyslij-prosbe/potwierdz/" in m.body
    )
    path = _link(message, "/wyslij-prosbe/potwierdz/")
    mail.outbox.clear()
    return client.post(path)


@pytest.mark.django_db
def test_submit_waits_for_the_senders_confirmation(client):
    response = _submit(client)

    assert response.json()["data"]["redirect_url"] == reverse(
        "public:guest-request-sent"
    )
    request_obj = Request.objects.get()
    assert request_obj.awaiting_confirmation
    owner = request_obj.created_by
    assert owner.email == "biuro@example.com"
    assert owner.display_name == "Biuro Nowak"
    assert not owner.has_usable_password()
    assert GuestAccess.objects.filter(user=owner).exists()
    # Only the sender hears about it - the recipient gets nothing yet.
    assert [m.to for m in mail.outbox] == [["biuro@example.com"]]
    assert "/wyslij-prosbe/potwierdz/" in mail.outbox[0].body


@pytest.mark.django_db
def test_opening_the_confirmation_link_does_not_send(client):
    _submit(client)
    path = _link(mail.outbox[0], "/wyslij-prosbe/potwierdz/")

    response = client.get(path)

    assert "Potwierdź i wyślij prośbę" in page_text(response)
    assert Request.objects.get().awaiting_confirmation


@pytest.mark.django_db
def test_pending_request_is_invisible_to_the_recipient(client):
    _submit(client)
    request_obj = Request.objects.get()
    Request.objects.filter(pk=request_obj.pk).update(
        created_at=timezone.now() - timedelta(days=10)
    )

    public = client.get(
        reverse("public:request-detail", args=[request_obj.public_token])
    )

    assert public.status_code == 404
    assert send_automatic_reminders() == 0


@pytest.mark.django_db
def test_confirming_sends_the_request_and_opens_the_panel(client):
    _submit(client, password="Tajne-Haslo-9")

    response = _confirm(client)

    request_obj = Request.objects.get()
    assert response.url == reverse("requests:detail", args=[request_obj.pk])
    assert not request_obj.awaiting_confirmation
    assert request_obj.pending_access_password == ""
    assert request_obj.created_by.email_verified_at is not None
    to_recipient = [m for m in mail.outbox if m.to == ["jan@example.com"]]
    assert len(to_recipient) == 2  # the link and, separately, the password
    assert any("Tajne-Haslo-9" in m.body for m in to_recipient)
    access = next(m for m in mail.outbox if m.to == ["biuro@example.com"])
    assert "/dostep/" in access.body
    # Logged in straight away.
    assert client.get(reverse("accounts:panel")).status_code == 200


@pytest.mark.django_db
def test_every_request_from_the_same_address_lands_in_one_panel(client):
    _submit(client)
    _confirm(client)
    owner = User.objects.get(email="biuro@example.com")
    first_link = guest_panel_url(owner)
    Request.objects.update(created_at=timezone.now() - timedelta(days=1))
    browser = BrowserClient()

    _submit(browser, ip="10.0.0.2", name="Dokumenty za październik")
    _confirm(browser)

    assert Request.objects.filter(created_by=owner).count() == 2
    assert guest_panel_url(owner) == first_link
    # The access email comes once; later confirmations don't repeat it.
    assert not any("/dostep/" in m.body for m in mail.outbox if m.to == [owner.email])


@pytest.mark.django_db
def test_the_permanent_link_logs_in(client):
    _submit(client)
    _confirm(client)
    owner = User.objects.get(email="biuro@example.com")
    browser = BrowserClient()

    response = browser.get(guest_panel_url(owner, "/przypomnienia/"))

    assert response.url == "/przypomnienia/"
    panel = browser.get(reverse("requests:list"))
    assert "Dokumenty za wrzesień" in page_text(panel)
    assert "Ustaw hasło" in page_text(panel)


@pytest.mark.django_db
def test_permanent_link_does_not_work_before_confirmation(client):
    _submit(client)
    owner = User.objects.get(email="biuro@example.com")

    response = BrowserClient().get(guest_panel_url(owner))

    assert response.status_code == 404


@pytest.mark.django_db
def test_passwordless_account_sends_one_request_a_day(client):
    _submit(client)
    _confirm(client)
    request_obj = Request.objects.get()

    with pytest.raises(Exception, match="wysłano już dziś"):
        RequestService.create(
            owner=request_obj.created_by,
            client_id=request_obj.client_id,
            name="Druga",
            description="",
            deadline=None,
            item_names=["A"],
        )


@pytest.mark.django_db
def test_the_public_form_is_limited_per_day_and_ip(client):
    _submit(client)

    response = _submit(BrowserClient(), sender_email="inny@example.com")

    assert response.status_code == 400
    assert "jedną prośbę" in response.json()["error"]["fields"]["__all__"][0]


@pytest.mark.django_db
def test_setting_a_password_turns_it_into_a_regular_account(client):
    _submit(client)
    _confirm(client)
    owner = User.objects.get(email="biuro@example.com")
    old_link = guest_panel_url(owner)

    response = client.post(
        reverse("accounts:settings"),
        {
            "form_action": "set_password",
            "new_password": "Nowe-Haslo-123!",
            "new_password_confirm": "Nowe-Haslo-123!",
        },
        **AJAX,
    )

    assert response.status_code == 200
    owner.refresh_from_db()
    assert owner.check_password("Nowe-Haslo-123!")
    assert not GuestAccess.objects.filter(user=owner).exists()
    assert BrowserClient().get(old_link).status_code == 404
    # Still logged in, and the daily limit is gone.
    assert client.get(reverse("accounts:panel")).status_code == 200
    RequestService.create(
        owner=owner,
        client_id=Client.objects.get(owner=owner).pk,
        name="Druga",
        description="",
        deadline=None,
        item_names=["A"],
    )


@pytest.mark.django_db
def test_sender_emails_point_to_the_permanent_link(client):
    _submit(client)
    _confirm(client)
    owner = User.objects.get(email="biuro@example.com")
    request_obj = Request.objects.get()
    for item in request_obj.items.all():
        UploadDocumentService.upload_for_item(
            item, make_pdf_upload(name=f"{item.pk}.pdf")
        )

    complete = next(
        m for m in mail.outbox if m.to == [owner.email] and "Komplet" in m.subject
    )
    assert f"/dostep/{owner.guest_access.token}/" in complete.body


@pytest.mark.django_db
def test_an_existing_account_is_used_but_not_logged_in(client, user):
    _submit(client, sender_email=user.email)

    response = _confirm(client, sender=user.email)

    request_obj = Request.objects.get()
    assert request_obj.created_by == user
    assert "Prośba wysłana" in page_text(response)
    assert client.get(reverse("accounts:panel")).status_code == 302


@pytest.mark.django_db
def test_confirmation_link_expires(client):
    _submit(client)
    Request.objects.update(created_at=timezone.now() - timedelta(hours=49))

    response = _confirm(client)

    assert response.status_code == 404
    assert Request.objects.get().awaiting_confirmation


@pytest.mark.django_db
def test_unconfirmed_requests_and_their_accounts_are_removed(client):
    _submit(client)
    User.objects.filter(email="biuro@example.com").update(
        date_joined=timezone.now() - timedelta(hours=49)
    )
    Request.objects.update(created_at=timezone.now() - timedelta(hours=49))

    assert GuestRequestService.delete_unconfirmed() == 1
    assert not Request.objects.exists()
    assert not Client.objects.exists()
    assert not User.objects.filter(email="biuro@example.com").exists()


@pytest.mark.django_db
def test_logged_in_users_send_requests_from_the_panel(client, user):
    client.force_login(user)

    response = client.get(reverse("public:guest-request-create"))

    assert response.url == reverse("requests:create")


@pytest.mark.django_db
def test_registering_with_a_passwordless_address_explains_what_to_do(client):
    _submit(client)
    _confirm(client)

    response = BrowserClient().post(
        reverse("accounts:register"),
        {
            "email": "biuro@example.com",
            "password": "Nowe-Haslo-123!",
            "password_confirm": "Nowe-Haslo-123!",
            "accept_terms": "on",
            "accept_privacy_policy": "on",
        },
        **AJAX,
    )

    assert "Nie pamiętasz hasła" in response.json()["error"]["fields"]["email"][0]


@pytest.mark.django_db
def test_passwordless_account_can_be_deleted_without_a_password(client):
    _submit(client)
    _confirm(client)

    response = client.post(
        reverse("accounts:settings"),
        {"form_action": "delete", "understood": "on"},
        **AJAX,
    )

    assert response.status_code == 200
    assert "/ustawienia/usun-konto/potwierdz/" in mail.outbox[-1].body
