import re

import pytest
from django.core import mail
from django.test import Client as BrowserClient
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.clients.models import Client
from apps.documents.services import UploadDocumentService
from apps.requests.models import RecipientAccess, Request
from apps.requests.services import RequestService
from tests.conftest import make_pdf_upload, page_text


def _send(owner, recipient_email, name, password=None):
    client_obj, _ = Client.objects.get_or_create(
        owner=owner, email=recipient_email, defaults={"name": "Odbiorca"}
    )
    return RequestService.create(
        owner=owner,
        client_id=client_obj.pk,
        name=name,
        description="",
        deadline=None,
        item_names=["Faktury"],
        password=password,
    )


def _portal_path(email):
    message = next(m for m in reversed(mail.outbox) if m.to == [email])
    return re.search(r"https?://[^\s]+(/moje-prosby/[^\s]+/)", message.body).group(1)


@pytest.fixture
def firm(db):
    return User.objects.create_user(
        email="biuro@example.com", password="x", display_name="Biuro Nowak"
    )


@pytest.fixture
def member(db):
    """A registered user who both sends and receives requests."""
    return User.objects.create_user(
        email="anna@example.com",
        password="x",
        display_name="Anna",
        email_verified_at=timezone.now(),
    )


@pytest.mark.django_db
def test_received_requests_show_up_in_the_account(client, firm, member):
    _send(firm, "ANNA@example.com", "Dokumenty do kredytu")
    _send(member, "ktos@example.com", "Moja własna prośba")
    client.force_login(member)

    content = page_text(client.get(reverse("requests:received")))

    assert "Dokumenty do kredytu" in content
    assert "Biuro Nowak" in content
    assert "Moja własna prośba" not in content


@pytest.mark.django_db
def test_finished_requests_stay_in_the_history_tab(client, firm, member):
    done = _send(firm, "anna@example.com", "Stara prośba")
    RequestService.close(done, actor=firm)
    _send(firm, "anna@example.com", "Nowa prośba")
    client.force_login(member)

    open_tab = page_text(client.get(reverse("requests:received")))
    history = page_text(client.get(reverse("requests:received") + "?widok=zakonczone"))

    assert "Nowa prośba" in open_tab and "Stara prośba" not in open_tab
    assert "Stara prośba" in history and "Nowa prośba" not in history


@pytest.mark.django_db
def test_unverified_address_does_not_reveal_received_requests(client, firm):
    _send(firm, "przejete@example.com", "Cudze dokumenty")
    impostor = User.objects.create_user(email="przejete@example.com", password="x")
    client.force_login(impostor)

    content = page_text(client.get(reverse("requests:received")))

    assert "Cudze dokumenty" not in content
    assert "Potwierdź swój adres" in content


@pytest.mark.django_db
def test_panel_counts_requests_waiting_for_my_documents(client, firm, member):
    _send(firm, "anna@example.com", "A")
    _send(firm, "anna@example.com", "B")
    client.force_login(member)

    content = client.get(reverse("accounts:panel")).content.decode()

    assert 'class="app-nav__count"' in content
    assert "received-banner" in content


@pytest.mark.django_db
def test_recipient_without_account_gets_a_panel_like_page(client, firm):
    closed = _send(firm, "jan@example.com", "Zamknięta")
    RequestService.close(closed, actor=firm)
    _send(firm, "jan@example.com", "Otwarta")
    path = _portal_path("jan@example.com")

    open_tab = page_text(client.get(path))
    history = page_text(client.get(path + "?widok=zakonczone"))

    assert "Otwarta" in open_tab and "Prześlij dokumenty" in open_tab
    assert "Zamknięta" in history


@pytest.mark.django_db
def test_recipient_page_points_account_holders_to_their_panel(client, firm, member):
    _send(firm, "anna@example.com", "Dokumenty")

    content = page_text(client.get(_portal_path("anna@example.com")))

    assert "Masz konto w Monituj" in content


@pytest.mark.django_db
def test_verified_recipient_skips_the_password_and_sees_all_their_files(firm):
    request_obj = _send(firm, "jan@example.com", "Z hasłem", password="Tajne-9!")
    path = _portal_path("jan@example.com")
    item = request_obj.items.get()
    UploadDocumentService.upload_for_item(item, make_pdf_upload(name="umowa.pdf"))
    detail = reverse("public:request-detail", args=[request_obj.public_token])

    stranger = page_text(BrowserClient().get(detail))
    recipient = BrowserClient()
    recipient.get(path)
    own_view = page_text(recipient.get(detail))

    assert "Podaj hasło" in stranger
    assert "umowa.pdf" in own_view
    # Files sent from another browser are shown but can't be deleted here.
    assert "delete-document" not in own_view


@pytest.mark.django_db
def test_browser_zone_is_stored_on_the_account(client, member):
    client.force_login(member)
    client.cookies["tz"] = "America/New_York"

    client.get(reverse("accounts:panel"))

    member.refresh_from_db()
    assert member.timezone == "America/New_York"


@pytest.mark.django_db
def test_made_up_zones_are_ignored(client, member):
    client.force_login(member)
    client.cookies["tz"] = "Mars/Olympus"

    client.get(reverse("accounts:panel"))

    member.refresh_from_db()
    assert member.timezone == "Europe/Warsaw"


@pytest.mark.django_db
def test_request_remembers_the_senders_zone(member):
    member.timezone = "Asia/Tokyo"
    member.save()

    request_obj = _send(member, "jan@example.com", "Dokumenty")

    assert request_obj.sender_timezone == "Asia/Tokyo"


@pytest.mark.django_db
def test_recipient_zone_is_learned_when_they_open_their_link(firm):
    request_obj = _send(firm, "jan@example.com", "Dokumenty")
    browser = BrowserClient()
    browser.cookies["tz"] = "America/Chicago"

    browser.get(reverse("public:request-detail", args=[request_obj.public_token]))

    access = RecipientAccess.objects.get(email="jan@example.com")
    assert access.timezone == "America/Chicago"
    assert Request.objects.get(pk=request_obj.pk)


@pytest.mark.django_db
def test_sender_without_account_gets_the_browser_zone(client):
    client.cookies["tz"] = "Europe/London"

    client.post(
        reverse("public:guest-request-create"),
        {
            "sender_name": "Jan",
            "sender_email": "nowy@example.com",
            "client_name": "Ola",
            "client_email": "ola@example.com",
            "name": "Dokumenty",
            "description": "",
            "items": ["A"],
            "password": "",
            "accept_terms": "on",
        },
    )

    request_obj = Request.objects.get(name="Dokumenty")
    assert request_obj.created_by.timezone == "Europe/London"
    assert request_obj.sender_timezone == "Europe/London"
