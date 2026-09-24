from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccountToken, AccountTokenPurpose, User
from apps.common.security import generate_public_token, hash_token

VALID_PASSWORD = "Sup3r-Secret-Pass!23"


@pytest.mark.django_db
def test_register_view_get_renders_form(client):
    response = client.get(reverse("accounts:register"))

    assert response.status_code == 200
    assert "Zarejestruj się".encode() in response.content
    assert b"Adres email" in response.content
    assert "Hasło".encode() in response.content
    assert b">Password<" not in response.content
    assert b">Email<" not in response.content


@pytest.mark.django_db
def test_register_view_post_creates_user_and_redirects(client):
    response = client.post(
        reverse("accounts:register"),
        {
            "email": "view-test@example.com",
            "password": VALID_PASSWORD,
            "password_confirm": VALID_PASSWORD,
            "accept_terms": "on",
            "accept_privacy_policy": "on",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("accounts:verification-sent")
    assert User.objects.filter(email="view-test@example.com").exists()


@pytest.mark.django_db
def test_register_view_post_password_mismatch_shows_error(client):
    response = client.post(
        reverse("accounts:register"),
        {
            "email": "mismatch@example.com",
            "password": VALID_PASSWORD,
            "password_confirm": "different",
            "accept_terms": "on",
            "accept_privacy_policy": "on",
        },
    )

    assert response.status_code == 200
    assert "Hasła nie są identyczne.".encode() in response.content
    assert not User.objects.filter(email="mismatch@example.com").exists()


@pytest.mark.django_db
def test_register_view_without_consent_shows_required_error(client):
    response = client.post(
        reverse("accounts:register"),
        {
            "email": "noconsent@example.com",
            "password": VALID_PASSWORD,
            "password_confirm": VALID_PASSWORD,
        },
    )

    assert response.status_code == 200
    assert not User.objects.filter(email="noconsent@example.com").exists()


@pytest.mark.django_db
def test_verify_email_view_accepts_valid_token(client):
    user = User.objects.create_user(
        email="verify-view@example.com", password=VALID_PASSWORD
    )
    raw_token = generate_public_token()
    AccountToken.objects.create(
        user=user,
        purpose=AccountTokenPurpose.EMAIL_VERIFICATION,
        token_hash=hash_token(raw_token),
        expires_at=timezone.now() + timedelta(hours=1),
    )

    response = client.get(reverse("accounts:verify-email", args=[raw_token]))

    assert response.status_code == 200
    assert b"Email zweryfikowany" in response.content
    user.refresh_from_db()
    assert user.is_email_verified is True


@pytest.mark.django_db
def test_verify_email_view_rejects_unknown_token(client):
    response = client.get(reverse("accounts:verify-email", args=["does-not-exist"]))

    assert response.status_code == 200
    assert "Nieprawidłowy link".encode() in response.content


@pytest.mark.django_db
def test_panel_requires_login_and_redirects_with_next(client):
    response = client.get(reverse("accounts:panel"))

    assert response.status_code == 302
    assert "logowanie" in response.url
    assert "next=" in response.url


@pytest.mark.django_db
def test_login_view_success_redirects_to_panel(client):
    User.objects.create_user(email="login-view@example.com", password=VALID_PASSWORD)

    response = client.post(
        reverse("accounts:login"),
        {"email": "login-view@example.com", "password": VALID_PASSWORD},
    )

    assert response.status_code == 302
    assert response.url == reverse("accounts:panel")

    panel_response = client.get(reverse("accounts:panel"))
    assert b"login-view@example.com" in panel_response.content


@pytest.mark.django_db
def test_login_view_already_authenticated_redirects_to_panel(client):
    User.objects.create_user(email="already@example.com", password=VALID_PASSWORD)
    client.post(
        reverse("accounts:login"),
        {"email": "already@example.com", "password": VALID_PASSWORD},
    )

    response = client.get(reverse("accounts:login"))

    assert response.status_code == 302
    assert response.url == reverse("accounts:panel")


@pytest.mark.django_db
def test_logout_view_rejects_get(client):
    response = client.get(reverse("accounts:logout"))

    assert response.status_code == 405


@pytest.mark.django_db
def test_logout_view_post_ends_session(client):
    User.objects.create_user(email="logout-view@example.com", password=VALID_PASSWORD)
    client.post(
        reverse("accounts:login"),
        {"email": "logout-view@example.com", "password": VALID_PASSWORD},
    )

    response = client.post(reverse("accounts:logout"))
    assert response.status_code == 302

    panel_response = client.get(reverse("accounts:panel"))
    assert panel_response.status_code == 302


@pytest.mark.django_db
def test_password_reset_request_view_does_not_reveal_account_existence(client):
    response = client.post(
        reverse("accounts:password-reset-request"), {"email": "nobody@example.com"}
    )

    assert response.status_code == 200
    assert "wysłaliśmy link".encode() in response.content


@pytest.mark.django_db
def test_password_reset_confirm_view_success(client):
    user = User.objects.create_user(
        email="reset-view@example.com", password=VALID_PASSWORD
    )
    raw_token = generate_public_token()
    AccountToken.objects.create(
        user=user,
        purpose=AccountTokenPurpose.PASSWORD_RESET,
        token_hash=hash_token(raw_token),
        expires_at=timezone.now() + timedelta(hours=1),
    )

    new_password = "Nowe-Bezpieczne-Haslo!5"
    response = client.post(
        reverse("accounts:password-reset-confirm", args=[raw_token]),
        {"password": new_password, "password_confirm": new_password},
    )

    assert response.status_code == 200
    assert "Hasło zmienione".encode() in response.content
    user.refresh_from_db()
    assert user.check_password(new_password)
