import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.common.exceptions import ValidationAppError
from apps.common.security import get_client_ip, hash_ip
from apps.documents import services as document_services
from apps.documents.services import UploadDocumentService
from apps.documents.validation import validate_upload
from apps.requests.forms import RequestEditForm
from apps.requests.models import Request
from apps.requests.services import RequestService
from tests.conftest import MINIMAL_PNG_BYTES, make_pdf_upload

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
PASSWORD = "Sup3r-Secret-Pass!23"


def _login(client, email, password=PASSWORD):
    return client.post(
        reverse("accounts:login"), {"email": email, "password": password}, **AJAX
    )


@pytest.fixture
def verified(db):
    return User.objects.create_user(
        email="anna@example.com", password=PASSWORD, email_verified_at=timezone.now()
    )


@pytest.mark.django_db
def test_login_is_blocked_after_repeated_failures(client, verified):
    for _ in range(8):
        _login(client, verified.email, "zle-haslo")

    response = _login(client, verified.email)

    assert response.status_code == 400
    assert "Zbyt wiele" in response.json()["error"]["message"]


@pytest.mark.django_db
def test_unconfirmed_account_cannot_log_in_but_gets_the_link_again(client):
    User.objects.create_user(email="nowy@example.com", password=PASSWORD)

    response = _login(client, "nowy@example.com")

    assert "potwierdź adres email" in response.json()["error"]["fields"]["email"][0]
    assert "/weryfikacja-email/" in mail.outbox[-1].body
    assert client.get(reverse("accounts:panel")).status_code == 302


@pytest.mark.django_db
def test_registering_an_unconfirmed_address_never_sets_the_password(client):
    """Whoever fills in the form must not choose the password of an account
    someone else will confirm - the inbox owner gets a set-password link."""
    squatter = User.objects.create_user(email="anna@example.com", password="Inne-9!x")

    response = client.post(
        reverse("accounts:register"),
        {
            "email": "anna@example.com",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "accept_terms": "on",
            "accept_privacy_policy": "on",
        },
        **AJAX,
    )

    assert response.status_code == 200
    squatter.refresh_from_db()
    assert squatter.check_password("Inne-9!x")
    assert not squatter.check_password(PASSWORD)
    assert "/reset-hasla/" in mail.outbox[-1].body


@pytest.mark.django_db
def test_confirmed_account_cannot_be_registered_again(client, verified):
    response = client.post(
        reverse("accounts:register"),
        {
            "email": verified.email,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "accept_terms": "on",
            "accept_privacy_policy": "on",
        },
        **AJAX,
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_password_reset_mails_are_limited_per_address(client, verified):
    for _ in range(5):
        client.post(
            reverse("accounts:password-reset-request"), {"email": verified.email}
        )

    assert len(mail.outbox) == 3


@pytest.mark.django_db
def test_request_password_cannot_be_guessed_endlessly(client, user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
        password="Tajne-Haslo-9",
    )
    url = reverse("public:request-detail", args=[request_obj.public_token])
    for _ in range(10):
        client.post(url, {"password": "zle"})

    response = client.post(url, {"password": "Tajne-Haslo-9"}, **AJAX)

    assert "Zbyt wiele" in response.json()["error"]["fields"]["password"][0]


@pytest.mark.django_db
def test_send_link_is_capped_per_day(client, verified, monkeypatch):
    from apps.requests import api

    monkeypatch.setattr(api, "SEND_LINK_PER_DAY", 2)
    client_obj = verified.clients.create(name="Jan", email="jan@example.com")
    request_obj = RequestService.create(
        owner=verified,
        client_id=client_obj.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
    )
    client.force_login(verified)
    url = reverse("requests_api:send-link", args=[request_obj.pk])
    for _ in range(2):
        client.post(url, {"email": "x@example.com"}, content_type="application/json")

    response = client.post(
        url, {"email": "x@example.com"}, content_type="application/json"
    )

    assert response.status_code == 429


@pytest.mark.django_db
def test_too_many_files_on_one_document_are_refused(request_item, monkeypatch):
    monkeypatch.setattr(document_services, "MAX_FILES_PER_ITEM", 1)
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload("a.pdf"))

    with pytest.raises(ValidationAppError, match="najwyżej 1"):
        UploadDocumentService.upload_for_item(
            request_item,
            SimpleUploadedFile("b.pdf", b"%PDF-1.4\n2\n%%EOF", "application/pdf"),
        )


def test_file_content_must_match_its_extension():
    image_as_pdf = SimpleUploadedFile("skan.pdf", MINIMAL_PNG_BYTES, "application/pdf")

    with pytest.raises(ValidationAppError):
        validate_upload(image_as_pdf)


def test_request_names_cannot_carry_line_breaks():
    form = RequestEditForm(data={"name": "Faktury\r\nBcc: x@y.pl", "description": ""})

    assert form.is_valid(), form.errors
    assert form.cleaned_data["name"] == "Faktury Bcc: x@y.pl"


def test_ip_hash_needs_the_secret_key(settings):
    first = hash_ip("1.2.3.4")
    settings.SECRET_KEY = "inny-klucz"

    assert hash_ip("1.2.3.4") != first


def test_client_ip_ignores_addresses_the_visitor_prepended():
    request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="6.6.6.6, 83.12.34.56")

    assert get_client_ip(request) == "83.12.34.56"


@pytest.mark.django_db
def test_guest_confirmation_link_uses_the_configured_site_address(client, settings):
    settings.SITE_URL = "https://monituj.pl"
    client.post(
        reverse("public:guest-request-create"),
        {
            "sender_name": "Jan",
            "sender_email": "jan@example.com",
            "client_name": "Ola",
            "client_email": "ola@example.com",
            "name": "R",
            "description": "",
            "items": ["A"],
            "password": "",
            "accept_terms": "on",
        },
        HTTP_HOST="evil.example",
    )

    assert "https://monituj.pl/wyslij-prosbe/potwierdz/" in mail.outbox[0].body
    assert Request.objects.exists()


@pytest.mark.django_db
def test_new_accounts_have_a_lower_daily_email_limit(verified, monkeypatch):
    from datetime import timedelta

    from apps.common.exceptions import RateLimitedAppError
    from apps.requests import services

    monkeypatch.setattr(services, "OUTBOUND_PER_DAY_NEW_ACCOUNT", 2)
    monkeypatch.setattr(services, "OUTBOUND_PER_DAY", 100)
    client_obj = verified.clients.create(name="Jan", email="jan@example.com")

    def send(name):
        return RequestService.create(
            owner=verified,
            client_id=client_obj.pk,
            name=name,
            description="",
            deadline=None,
            item_names=["A"],
        )

    send("A")
    send("B")
    with pytest.raises(RateLimitedAppError):
        send("C")
    # Refused before anything was stored or sent.
    assert not Request.objects.filter(name="C").exists()

    User.objects.filter(pk=verified.pk).update(
        date_joined=timezone.now() - timedelta(days=30)
    )
    verified.refresh_from_db()
    send("D")


def test_company_name_cannot_carry_line_breaks():
    from apps.accounts.forms import ProfileForm

    form = ProfileForm(data={"display_name": "Biuro\r\nBcc: x@y.pl"})

    assert form.is_valid()
    assert form.cleaned_data["display_name"] == "Biuro Bcc: x@y.pl"


@pytest.mark.django_db
def test_old_throttle_records_are_cleaned_up():
    from datetime import timedelta

    from apps.common.models import ThrottleEvent
    from apps.common.tasks import delete_old_throttle_events

    old = ThrottleEvent.objects.create(key="x")
    ThrottleEvent.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=2)
    )
    ThrottleEvent.objects.create(key="y")

    assert delete_old_throttle_events() == 1
    assert list(ThrottleEvent.objects.values_list("key", flat=True)) == ["y"]
