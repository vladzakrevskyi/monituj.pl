"""Every progressive-enhancement form in the app also accepts an AJAX
submission (marked by the X-Requested-With header ajax_form.js sends) and
responds with the same JSON envelope the API layer uses, instead of
re-rendering the HTML page. These tests drive that header directly with the
Django test client, independent of the client-side JS."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccountToken, AccountTokenPurpose, User
from apps.clients.models import Client
from apps.common.security import generate_public_token, hash_token
from apps.requests.services import RequestService

VALID_PASSWORD = "Sup3r-Secret-Pass!23"

AJAX_HEADERS = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


@pytest.mark.django_db
def test_register_ajax_success_returns_redirect_url(client):
    response = client.post(
        reverse("accounts:register"),
        {
            "email": "ajax-register@example.com",
            "password": VALID_PASSWORD,
            "password_confirm": VALID_PASSWORD,
            "accept_terms": "on",
            "accept_privacy_policy": "on",
        },
        **AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["redirect_url"] == reverse("accounts:verification-sent")
    assert User.objects.filter(email="ajax-register@example.com").exists()


@pytest.mark.django_db
def test_register_ajax_validation_error_returns_field_errors(client):
    response = client.post(
        reverse("accounts:register"),
        {
            "email": "ajax-mismatch@example.com",
            "password": VALID_PASSWORD,
            "password_confirm": "different",
            "accept_terms": "on",
            "accept_privacy_policy": "on",
        },
        **AJAX_HEADERS,
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "Hasła nie są identyczne." in payload["error"]["fields"]["password_confirm"]
    assert not User.objects.filter(email="ajax-mismatch@example.com").exists()


@pytest.mark.django_db
def test_register_non_ajax_still_returns_html_on_error(client):
    response = client.post(
        reverse("accounts:register"),
        {
            "email": "plain@example.com",
            "password": VALID_PASSWORD,
            "password_confirm": "different",
            "accept_terms": "on",
            "accept_privacy_policy": "on",
        },
    )

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    assert "Hasła nie są identyczne.".encode() in response.content


@pytest.mark.django_db
def test_login_ajax_success_returns_redirect_url(client):
    User.objects.create_user(email="ajax-login@example.com", password=VALID_PASSWORD)

    response = client.post(
        reverse("accounts:login"),
        {"email": "ajax-login@example.com", "password": VALID_PASSWORD},
        **AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["redirect_url"] == reverse("accounts:panel")


@pytest.mark.django_db
def test_login_ajax_invalid_credentials_returns_password_field_error(client):
    User.objects.create_user(email="ajax-login2@example.com", password=VALID_PASSWORD)

    response = client.post(
        reverse("accounts:login"),
        {"email": "ajax-login2@example.com", "password": "wrong"},
        **AJAX_HEADERS,
    )

    assert response.status_code == 400
    payload = response.json()
    assert (
        "Nieprawidłowy adres email lub hasło." in payload["error"]["fields"]["password"]
    )


@pytest.mark.django_db
def test_password_reset_request_ajax_returns_message_without_redirect(client):
    response = client.post(
        reverse("accounts:password-reset-request"),
        {"email": "someone@example.com"},
        **AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert "message" in payload["data"]
    assert "redirect_url" not in payload["data"]


@pytest.mark.django_db
def test_password_reset_confirm_ajax_success_and_error(client):
    user = User.objects.create_user(
        email="ajax-reset@example.com", password=VALID_PASSWORD
    )
    raw_token = generate_public_token()
    AccountToken.objects.create(
        user=user,
        purpose=AccountTokenPurpose.PASSWORD_RESET,
        token_hash=hash_token(raw_token),
        expires_at=timezone.now() + timedelta(hours=1),
    )

    bad_response = client.post(
        reverse("accounts:password-reset-confirm", args=[raw_token]),
        {"password": "weak", "password_confirm": "weak"},
        **AJAX_HEADERS,
    )
    assert bad_response.status_code == 400
    assert bad_response.json()["success"] is False

    ok_response = client.post(
        reverse("accounts:password-reset-confirm", args=[raw_token]),
        {
            "password": "Kolejne-Bezpieczne-Haslo!9",
            "password_confirm": "Kolejne-Bezpieczne-Haslo!9",
        },
        **AJAX_HEADERS,
    )
    assert ok_response.status_code == 200
    payload = ok_response.json()
    assert payload["data"]["title"] == "Hasło zmienione"


@pytest.fixture
def settings_user(db):
    return User.objects.create_user(
        email="ajax-settings@example.com", password=VALID_PASSWORD
    )


@pytest.mark.django_db
def test_settings_profile_ajax_success(client, settings_user):
    client.force_login(settings_user)

    response = client.post(
        reverse("accounts:settings"),
        {"form_action": "profile", "display_name": "Nowa Nazwa Ajax"},
        **AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["message"] == "Dane zostały zapisane."
    settings_user.refresh_from_db()
    assert settings_user.display_name == "Nowa Nazwa Ajax"


@pytest.mark.django_db
def test_settings_password_ajax_wrong_current_password_returns_field_error(
    client, settings_user
):
    client.force_login(settings_user)

    response = client.post(
        reverse("accounts:settings"),
        {
            "form_action": "password",
            "current_password": "wrong",
            "new_password": "Nowe-Bezpieczne-Haslo!1",
            "new_password_confirm": "Nowe-Bezpieczne-Haslo!1",
        },
        **AJAX_HEADERS,
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert (
        "Nieprawidłowe obecne hasło." in payload["error"]["fields"]["current_password"]
    )


@pytest.mark.django_db
def test_settings_password_ajax_success_does_not_redirect(client, settings_user):
    client.force_login(settings_user)

    response = client.post(
        reverse("accounts:settings"),
        {
            "form_action": "password",
            "current_password": VALID_PASSWORD,
            "new_password": "Nowe-Bezpieczne-Haslo!1",
            "new_password_confirm": "Nowe-Bezpieczne-Haslo!1",
        },
        **AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert "message" in payload["data"]
    assert "redirect_url" not in payload["data"]


@pytest.mark.django_db
def test_settings_email_ajax_taken_email_returns_field_error(client, settings_user):
    User.objects.create_user(email="taken-ajax@example.com", password=VALID_PASSWORD)
    client.force_login(settings_user)

    response = client.post(
        reverse("accounts:settings"),
        {
            "form_action": "email",
            "new_email": "taken-ajax@example.com",
            "current_password": VALID_PASSWORD,
        },
        **AJAX_HEADERS,
    )

    assert response.status_code == 400
    payload = response.json()
    assert "Ten adres email jest już zajęty." in payload["error"]["fields"]["new_email"]


@pytest.mark.django_db
def test_client_create_ajax_success_returns_redirect_url(client, user):
    client.force_login(user)

    response = client.post(
        reverse("clients:create"),
        {"name": "Nowy klient", "email": "nowy-klient@example.com"},
        **AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["redirect_url"] == reverse("clients:list")
    assert Client.objects.filter(owner=user, email="nowy-klient@example.com").exists()


@pytest.mark.django_db
def test_client_create_ajax_missing_name_returns_field_error(client, user):
    client.force_login(user)

    response = client.post(
        reverse("clients:create"),
        {"name": "", "email": "brak-nazwy@example.com"},
        **AJAX_HEADERS,
    )

    assert response.status_code == 400
    payload = response.json()
    assert "name" in payload["error"]["fields"]


@pytest.mark.django_db
def test_request_create_ajax_success_returns_redirect_url(client, user, client_record):
    client.force_login(user)

    response = client.post(
        reverse("requests:create"),
        {
            "client": client_record.pk,
            "name": "Dokumenty ajax",
            "description": "",
            "items": ["A"],
            "password": "",
        },
        **AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert "/przypomnienia/" in payload["data"]["redirect_url"]


@pytest.mark.django_db
def test_request_create_ajax_without_items_returns_items_field_error(
    client, user, client_record
):
    client.force_login(user)

    response = client.post(
        reverse("requests:create"),
        {"client": client_record.pk, "name": "Bez dokumentów", "description": ""},
        **AJAX_HEADERS,
    )

    assert response.status_code == 400
    payload = response.json()
    assert (
        "Dodaj co najmniej jeden dokument do listy."
        in payload["error"]["fields"]["items"]
    )


@pytest.mark.django_db
def test_request_edit_ajax_success_returns_redirect_url(client, user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Stara nazwa",
        description="",
        deadline=None,
        item_names=["A"],
    )
    client.force_login(user)

    response = client.post(
        reverse("requests:edit", args=[request_obj.pk]),
        {"name": "Nowa nazwa", "description": ""},
        **AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["redirect_url"] == reverse(
        "requests:detail", args=[request_obj.pk]
    )
    request_obj.refresh_from_db()
    assert request_obj.name == "Nowa nazwa"


@pytest.mark.django_db
def test_password_gate_ajax_wrong_password_returns_field_error(user, client_record):
    from django.test import Client as TestClient

    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
        password="Sekretne-Haslo!1",
    )
    gate_client = TestClient()

    response = gate_client.post(
        reverse("public:request-detail", args=[request_obj.public_token]),
        {"password": "wrong"},
        **AJAX_HEADERS,
    )

    assert response.status_code == 400
    payload = response.json()
    assert "Nieprawidłowe hasło." in payload["error"]["fields"]["password"]


@pytest.mark.django_db
def test_password_gate_ajax_correct_password_returns_redirect_url(user, client_record):
    from django.test import Client as TestClient

    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
        password="Sekretne-Haslo!1",
    )
    gate_client = TestClient()

    response = gate_client.post(
        reverse("public:request-detail", args=[request_obj.public_token]),
        {"password": "Sekretne-Haslo!1"},
        **AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["redirect_url"] == reverse(
        "public:request-detail", args=[request_obj.public_token]
    )
