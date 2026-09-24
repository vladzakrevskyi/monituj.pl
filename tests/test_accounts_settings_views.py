import pytest
from django.urls import reverse

from apps.accounts.models import AccountToken, AccountTokenPurpose, User
from apps.common.security import generate_public_token, hash_token
from tests.conftest import page_text

VALID_PASSWORD = "Sup3r-Secret-Pass!23"


@pytest.fixture
def settings_user(db):
    return User.objects.create_user(
        email="settings-user@example.com", password=VALID_PASSWORD
    )


def _reuse_pending_token(user, purpose):
    token = AccountToken.objects.get(user=user, purpose=purpose, used_at__isnull=True)
    raw_token = generate_public_token()
    token.token_hash = hash_token(raw_token)
    token.save(update_fields=["token_hash"])
    return raw_token


@pytest.mark.django_db
def test_settings_view_requires_login(client):
    response = client.get(reverse("accounts:settings"))

    assert response.status_code == 302
    assert "logowanie" in response.url


@pytest.mark.django_db
def test_settings_view_get_shows_current_display_name(client, settings_user):
    settings_user.display_name = "Moja Firma"
    settings_user.save(update_fields=["display_name"])
    client.force_login(settings_user)

    response = client.get(reverse("accounts:settings"))

    assert response.status_code == 200
    assert b"Moja Firma" in response.content
    assert settings_user.email.encode() in response.content


@pytest.mark.django_db
def test_settings_profile_update_saves_display_name(client, settings_user):
    client.force_login(settings_user)

    response = client.post(
        reverse("accounts:settings"),
        {"form_action": "profile", "display_name": "Nowa Nazwa"},
        follow=True,
    )

    assert response.status_code == 200
    settings_user.refresh_from_db()
    assert settings_user.display_name == "Nowa Nazwa"
    assert "Dane zostały zapisane.".encode() in response.content


@pytest.mark.django_db
def test_settings_password_change_wrong_current_password_shows_error(
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
    )

    assert response.status_code == 200
    assert "Nieprawidłowe obecne hasło.".encode() in response.content
    assert not AccountToken.objects.filter(
        user=settings_user, purpose=AccountTokenPurpose.PASSWORD_CHANGE
    ).exists()


@pytest.mark.django_db
def test_settings_password_change_mismatched_confirmation_shows_error(
    client, settings_user
):
    client.force_login(settings_user)

    response = client.post(
        reverse("accounts:settings"),
        {
            "form_action": "password",
            "current_password": VALID_PASSWORD,
            "new_password": "Nowe-Bezpieczne-Haslo!1",
            "new_password_confirm": "Cos-Innego!2",
        },
    )

    assert response.status_code == 200
    assert "Hasła nie są identyczne.".encode() in response.content


@pytest.mark.django_db
def test_settings_password_change_request_sends_email_and_does_not_change_yet(
    client, settings_user
):
    client.force_login(settings_user)

    response = client.post(
        reverse("accounts:settings"),
        {
            "form_action": "password",
            "current_password": VALID_PASSWORD,
            "new_password": "Nowe-Bezpieczne-Haslo!1",
            "new_password_confirm": "Nowe-Bezpieczne-Haslo!1",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert "Wysłaliśmy link potwierdzający zmianę hasła".encode() in response.content
    settings_user.refresh_from_db()
    assert settings_user.check_password(VALID_PASSWORD)


@pytest.mark.django_db
def test_settings_email_change_request_rejects_taken_email(client, settings_user):
    User.objects.create_user(email="taken@example.com", password=VALID_PASSWORD)
    client.force_login(settings_user)

    response = client.post(
        reverse("accounts:settings"),
        {
            "form_action": "email",
            "new_email": "taken@example.com",
            "current_password": VALID_PASSWORD,
        },
    )

    assert response.status_code == 200
    assert "Ten adres email jest już zajęty.".encode() in response.content


@pytest.mark.django_db
def test_settings_email_change_request_sends_confirmation(client, settings_user):
    client.force_login(settings_user)

    response = client.post(
        reverse("accounts:settings"),
        {
            "form_action": "email",
            "new_email": "nowy@example.com",
            "current_password": VALID_PASSWORD,
        },
        follow=True,
    )

    assert response.status_code == 200
    assert "Wysłaliśmy link potwierdzający na nowy adres email." in page_text(response)
    settings_user.refresh_from_db()
    assert settings_user.email == "settings-user@example.com"


@pytest.mark.django_db
def test_password_change_confirm_get_does_not_require_login(client, settings_user):
    response = client.get(
        reverse("accounts:password-change-confirm", args=["whatever-token"])
    )

    assert response.status_code == 200
    assert "Potwierdź zmianę hasła".encode() in response.content


@pytest.mark.django_db
def test_password_change_confirm_logs_out_the_requesting_session_everywhere(
    client, settings_user
):
    """The whole point of gating on an emailed link: confirming never
    refreshes any session's auth hash, so the session that requested the
    change - not just other devices - gets logged out too."""
    client.force_login(settings_user)
    client.post(
        reverse("accounts:settings"),
        {
            "form_action": "password",
            "current_password": VALID_PASSWORD,
            "new_password": "Nowe-Bezpieczne-Haslo!1",
            "new_password_confirm": "Nowe-Bezpieczne-Haslo!1",
        },
    )
    raw_token = _reuse_pending_token(settings_user, AccountTokenPurpose.PASSWORD_CHANGE)

    confirm_response = client.post(
        reverse("accounts:password-change-confirm", args=[raw_token])
    )
    assert confirm_response.status_code == 200
    assert "Hasło zmienione".encode() in confirm_response.content

    panel_response = client.get(reverse("accounts:panel"))
    assert panel_response.status_code == 302
    assert "logowanie" in panel_response.url


@pytest.mark.django_db
def test_password_change_confirm_works_from_a_fresh_unauthenticated_client(
    client, settings_user
):
    """Clicking the emailed link from a different device/browser than the
    one that requested the change must still work."""
    client.force_login(settings_user)
    client.post(
        reverse("accounts:settings"),
        {
            "form_action": "password",
            "current_password": VALID_PASSWORD,
            "new_password": "Nowe-Bezpieczne-Haslo!1",
            "new_password_confirm": "Nowe-Bezpieczne-Haslo!1",
        },
    )
    raw_token = _reuse_pending_token(settings_user, AccountTokenPurpose.PASSWORD_CHANGE)

    from django.test import Client as TestClient

    fresh_client = TestClient()
    response = fresh_client.post(
        reverse("accounts:password-change-confirm", args=[raw_token])
    )

    assert response.status_code == 200
    assert "Hasło zmienione".encode() in response.content
    settings_user.refresh_from_db()
    assert settings_user.check_password("Nowe-Bezpieczne-Haslo!1")


@pytest.mark.django_db
def test_password_change_confirm_invalid_token_shows_error(client):
    response = client.post(
        reverse("accounts:password-change-confirm", args=["bogus-token"])
    )

    assert response.status_code == 200
    assert "Nieprawidłowy link".encode() in response.content


@pytest.mark.django_db
def test_email_change_confirm_applies_new_email(client, settings_user):
    client.force_login(settings_user)
    client.post(
        reverse("accounts:settings"),
        {
            "form_action": "email",
            "new_email": "potwierdzony@example.com",
            "current_password": VALID_PASSWORD,
        },
    )
    raw_token = _reuse_pending_token(settings_user, AccountTokenPurpose.EMAIL_CHANGE)

    response = client.post(reverse("accounts:email-change-confirm", args=[raw_token]))

    assert response.status_code == 200
    assert b"Email zmieniony" in response.content
    settings_user.refresh_from_db()
    assert settings_user.email == "potwierdzony@example.com"


@pytest.mark.django_db
def test_email_change_confirm_invalid_token_shows_error(client):
    response = client.post(
        reverse("accounts:email-change-confirm", args=["bogus-token"])
    )

    assert response.status_code == 200
    assert "Nieprawidłowy link".encode() in response.content
