"""A new account goes straight to its first request; what it sends waits
for the confirmation link and goes out when it's clicked - never from an
address nobody has proved (apps/requests/services.awaits_verification)."""

import re

import pytest
from django.core import mail
from django.urls import reverse

from apps.accounts.models import User
from apps.clients.models import Client
from apps.common.exceptions import ValidationAppError
from apps.requests.models import Request
from apps.requests.services import RequestService
from tests.conftest import page_text

PASSWORD = "Sup3r-Secret-Pass!23"


def _register(client, email="nowe@biuro.pl"):
    return client.post(
        reverse("accounts:register"),
        {"email": email, "password": PASSWORD, "accept_terms": "on"},
    )


def _confirm_path():
    [message] = [m for m in mail.outbox if "/weryfikacja-email/" in m.body]
    return re.search(r"/weryfikacja-email/[^/\s]+/", message.body)[0]


def _send(owner, email="klient@example.com"):
    client_obj = Client.objects.create(owner=owner, name="Klient", email=email)
    return RequestService.create(
        owner=owner,
        client_id=client_obj.pk,
        name="Dokumenty za październik",
        description="",
        deadline=None,
        item_names=["Wyciąg bankowy"],
    )


def _to_client():
    return [m for m in mail.outbox if m.to == ["klient@example.com"]]


@pytest.mark.django_db
def test_registration_signs_in_and_opens_the_first_request(client):
    response = _register(client)

    assert response.url == reverse("requests:create")
    user = User.objects.get(email="nowe@biuro.pl")
    assert user.email_verified_at is None
    assert client.get(reverse("requests:create")).status_code == 200


@pytest.mark.django_db
def test_one_checkbox_and_no_repeated_password(client):
    page = page_text(client.get(reverse("accounts:register")))

    assert "Powtórz hasło" not in page
    assert 'name="password_confirm"' not in page
    assert 'name="accept_privacy_policy"' not in page
    assert 'name="accept_terms"' in page


@pytest.mark.django_db
def test_a_request_waits_and_the_panel_says_so(client):
    _register(client)
    user = User.objects.get(email="nowe@biuro.pl")

    request_obj = _send(user)

    assert request_obj.awaiting_confirmation
    assert not _to_client()
    page = page_text(client.get(reverse("accounts:panel")))
    assert "Prośba czeka na wysłanie" in page
    detail = page_text(client.get(request_obj.panel_url()))
    assert "gdy potwierdzisz adres" in detail


@pytest.mark.django_db
def test_confirming_shows_what_goes_out_and_sends_it(client):
    _register(client)
    user = User.objects.get(email="nowe@biuro.pl")
    request_obj = _send(user)
    path = _confirm_path()

    page = page_text(client.get(path))
    response = client.post(path)

    assert "Dokumenty za październik" in page and "klient@example.com" in page
    assert response.url == reverse("requests:list")
    request_obj.refresh_from_db()
    assert not request_obj.awaiting_confirmation
    [invitation] = _to_client()
    assert request_obj.public_token in invitation.body


@pytest.mark.django_db
def test_nothing_else_reaches_anyone_before_confirming(client):
    _register(client)
    user = User.objects.get(email="nowe@biuro.pl")
    request_obj = _send(user)

    with pytest.raises(ValidationAppError):
        RequestService.send_invitation(request_obj, "ktos@example.com")
    with pytest.raises(ValidationAppError):
        from apps.accounts import team

        team.invite(user, "anna@example.com")
    assert not [m for m in mail.outbox if "@biuro.pl" not in m.to[0]]


@pytest.mark.django_db
def test_held_requests_stay_held_after_a_password_reset(client, settings):
    """Someone else may have prepared them: the owner sends them by hand."""
    from apps.accounts.services import PasswordResetService

    _register(client)
    user = User.objects.get(email="nowe@biuro.pl")
    request_obj = _send(user)
    PasswordResetService.request_reset(user.email)
    raw = re.search(r"/reset-hasla/([^/\s]+)/", mail.outbox[-1].body)[1]

    PasswordResetService.confirm_reset(raw, "Nowe-Haslo-123!x")

    request_obj.refresh_from_db()
    assert request_obj.awaiting_confirmation
    assert not _to_client()
    user.refresh_from_db()  # the new password
    client.force_login(user)
    assert "Wyślij teraz" in page_text(client.get(request_obj.panel_url()))
    client.post(reverse("requests:send-held", args=[request_obj.pk]))
    request_obj.refresh_from_db()
    assert not request_obj.awaiting_confirmation
    assert len(_to_client()) == 1


@pytest.mark.django_db
def test_someone_elses_unconfirmed_address_gets_no_session(client):
    User.objects.create_user(email="zajety@biuro.pl", password="Inne-9!x")

    response = _register(client, "zajety@biuro.pl")

    assert response.url == reverse("accounts:verification-sent")
    assert client.get(reverse("accounts:panel")).status_code == 302


@pytest.mark.django_db
def test_an_unconfirmed_account_cant_join_a_team(client, user):
    from apps.accounts import team

    _register(client, "anna@biuro.pl")
    anna = User.objects.get(email="anna@biuro.pl")
    invitation = team.invite(user, "anna@biuro.pl")

    with pytest.raises(ValidationAppError):
        team.join_as_existing(invitation, anna, None)


@pytest.mark.django_db
def test_held_requests_are_not_deleted_like_unconfirmed_guest_ones(client):
    from datetime import timedelta

    from django.utils import timezone

    from apps.requests.guest import GuestRequestService

    _register(client)
    request_obj = _send(User.objects.get(email="nowe@biuro.pl"))
    Request.objects.filter(pk=request_obj.pk).update(
        created_at=timezone.now() - timedelta(days=5)
    )

    GuestRequestService.delete_unconfirmed()

    assert Request.objects.filter(pk=request_obj.pk).exists()
