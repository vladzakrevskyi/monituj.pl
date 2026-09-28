import pytest
from django.core import mail
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.sender import is_deceptive
from apps.billing.models import BillingProfile
from apps.clients.models import Client
from apps.requests.models import Request
from tests.conftest import page_text
from tests.test_guest_requests import _submit

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def _text(value):
    return value.replace(" ", " ")


def _verified_firm(user, source="GUS"):
    return BillingProfile.objects.create(
        user=user,
        kind="company",
        company_name="BIURO TESTOWE SP. Z O.O.",
        tax_id="5213017228",
        street="ul. Prosta 1",
        post_code="00-001",
        city="Warszawa",
        registry_source=source,
    )


def _create(client, owner_client, **extra):
    data = {
        "client": owner_client.pk,
        "name": "Dokumenty za wrzesień",
        "items": ["Faktury"],
        "retention_choice": "90",
        **extra,
    }
    return client.post(reverse("requests:create"), data, **AJAX)


# --- 1. The confirmed address next to the name -----------------------------------


@pytest.mark.django_db
def test_recipients_see_the_senders_confirmed_address(client, user, client_record):
    client.force_login(user)

    _create(client, client_record)

    message = mail.outbox[-1]
    body = _text(message.body)
    html = _text(message.alternatives[0][0])
    assert "Od: Biuro Testowe (owner@example.com)" in body
    assert "Biuro Testowe (owner@example.com)" in html
    assert "Biuro Testowe" in message.subject


@pytest.mark.django_db
def test_request_page_shows_the_senders_address(client, user, client_record):
    client.force_login(user)
    _create(client, client_record)
    request_obj = Request.objects.get()
    client.logout()

    html = page_text(
        client.get(reverse("public:request-detail", args=[request_obj.public_token]))
    )

    assert "Od: <strong>Biuro Testowe</strong>" in html
    assert "(owner@example.com)" in html


# --- 2. Verified firm ---------------------------------------------------------------


@pytest.mark.django_db
def test_verified_firm_is_named_in_emails_and_on_the_page(client, user, client_record):
    _verified_firm(user)
    client.force_login(user)
    _create(client, client_record)
    request_obj = Request.objects.get()
    client.logout()

    html = page_text(
        client.get(reverse("public:request-detail", args=[request_obj.public_token]))
    )

    assert "Firma zweryfikowana: BIURO TESTOWE SP. Z O.O., NIP 5213017228" in _text(
        mail.outbox[-1].body
    )
    assert "Firma zweryfikowana w rejestrze: BIURO TESTOWE SP. Z O.O." in html


@pytest.mark.django_db
def test_typed_in_firm_is_not_called_verified(client, user, client_record):
    _verified_firm(user, source="")
    client.force_login(user)

    _create(client, client_record)

    assert "Firma zweryfikowana" not in mail.outbox[-1].body


# --- 3. A name before the first request ---------------------------------------------


@pytest.mark.django_db
def test_first_request_asks_how_to_introduce_the_sender(client):
    owner = User.objects.create_user(email="nowy@example.com", password="x-pass-123!")
    firm = Client.objects.create(owner=owner, name="Klient", email="k@example.com")
    _verified_firm(owner)
    client.force_login(owner)

    form = page_text(client.get(reverse("requests:create")))
    missing = _create(client, firm)
    created = _create(client, firm, sender_name="Kancelaria Nowak")

    # Suggested from the invoice details.
    assert 'value="BIURO TESTOWE SP. Z O.O."' in form
    assert "Jak przedstawić Cię klientowi?" in form
    assert "sender_name" in missing.json()["error"]["fields"]
    assert created.status_code == 200
    owner.refresh_from_db()
    assert owner.display_name == "Kancelaria Nowak"
    # Asked once.
    assert "Jak przedstawić Cię klientowi?" not in page_text(
        client.get(reverse("requests:create"))
    )


@pytest.mark.django_db
def test_api_needs_the_name_too(client):
    owner = User.objects.create_user(email="api@example.com", password="x-pass-123!")
    firm = Client.objects.create(owner=owner, name="Klient", email="k@example.com")
    client.force_login(owner)

    response = client.post(
        "/api/requests/",
        {"client": firm.pk, "name": "R", "items": ["A"]},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "przedstawić" in response.json()["error"]["message"]


# --- 4. Names that mimic institutions ------------------------------------------------


@pytest.mark.parametrize(
    ("name", "deceptive"),
    [
        ("Urząd Skarbowy w Krakowie", True),
        ("Zakład Ubezpieczeń Społecznych", True),
        ("ZUS", True),
        ("Sąd Rejonowy", True),
        ("PKO Bank Polski", True),
        ("mBank", True),
        ("Monituj", True),
        ("Kancelaria Sadowski", False),
        ("Urządzenia Chłodnicze Sp. z o.o.", False),
        ("Biuro Rachunkowe Bankowa", False),
        ("Jan Kowalski", False),
    ],
)
def test_deceptive_names(name, deceptive):
    assert is_deceptive(name) is deceptive


@pytest.mark.django_db
def test_settings_refuse_a_deceptive_name(client, user):
    client.force_login(user)

    client.post(
        reverse("accounts:settings"),
        {"form_action": "profile", "display_name": "Urząd Skarbowy"},
    )

    user.refresh_from_db()
    assert user.display_name == "Biuro Testowe"


@pytest.mark.django_db
def test_request_form_refuses_a_deceptive_name(client):
    owner = User.objects.create_user(email="nowy@example.com", password="x-pass-123!")
    firm = Client.objects.create(owner=owner, name="Klient", email="k@example.com")
    client.force_login(owner)

    response = _create(client, firm, sender_name="ZUS Oddział Kraków")

    assert (
        "wprowadzać odbiorców w błąd"
        in response.json()["error"]["fields"]["sender_name"][0]
    )
    assert not Request.objects.exists()


@pytest.mark.django_db
def test_no_account_form_refuses_a_deceptive_name(client):
    response = _submit(client, sender_name="Policja")

    assert "sender_name" in response.json()["error"]["fields"]
