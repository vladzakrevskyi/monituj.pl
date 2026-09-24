import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core import mail
from django.test import Client as BrowserClient
from django.urls import reverse

from apps.accounts import google
from apps.accounts.models import GoogleAccount, GuestAccess, User
from apps.demo.models import DemoAccount
from tests.conftest import page_text

CLIENT_ID = "test-client.apps.googleusercontent.com"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def google_on(settings, monkeypatch):
    settings.GOOGLE_OAUTH_CLIENT_ID = CLIENT_ID
    settings.GOOGLE_OAUTH_CLIENT_SECRET = "test-secret"
    monkeypatch.setattr(
        google,
        "_jwks",
        SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=KEY.public_key())
        ),
    )
    issued = {}

    def fake_exchange(code, verifier):
        issued["verifier"] = verifier
        return issued["token"]

    monkeypatch.setattr(google, "_exchange_code", fake_exchange)
    return issued


def _token(nonce, key=KEY, **overrides):
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "azp": CLIENT_ID,
        "sub": "google-sub-1",
        "email": "jan@gmail.com",
        "email_verified": True,
        "iat": now,
        "exp": now + 3600,
        "nonce": nonce,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256")


def _google(browser, issued, start="accounts:google-start", key=KEY, **claims):
    """Runs the whole round trip: button, Google, callback."""
    started = browser.get(reverse(start))
    flow = browser.session.get("google_oauth")
    assert flow, started
    issued["token"] = _token(flow["nonce"], key=key, **claims)
    return browser.get(
        reverse("accounts:google-callback"), {"state": flow["state"], "code": "c"}
    )


def _logged_in_as(browser):
    user_id = browser.session.get("_auth_user_id")
    return User.objects.get(pk=user_id) if user_id else None


def _accept_terms(browser):
    return browser.post(
        reverse("accounts:google-signup"),
        {"accept_terms": "on", "accept_privacy_policy": "on"},
    )


def _confirm_link(email):
    body = next(m for m in mail.outbox if m.to == [email]).body
    return next(w for w in body.split() if "/logowanie/google/potwierdz/" in w)


# --- switched off / the button ---------------------------------------------


@pytest.mark.django_db
def test_without_configuration_there_is_no_google_at_all(client, settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = ""

    assert "google" not in client.get(reverse("accounts:login")).content.decode()
    assert client.get(reverse("accounts:google-start")).status_code == 404
    assert client.get(reverse("accounts:google-callback")).status_code == 404


@pytest.mark.django_db
def test_buttons_on_login_and_register(client, google_on):
    for name in ("accounts:login", "accounts:register"):
        assert (
            reverse("accounts:google-start")
            in client.get(reverse(name)).content.decode()
        )


@pytest.mark.django_db
def test_start_sends_to_google_with_pkce_state_and_nonce(client, google_on):
    response = client.get(reverse("accounts:google-start"))
    query = parse_qs(urlparse(response["Location"]).query)
    flow = client.session["google_oauth"]

    assert response["Location"].startswith(google.AUTHORIZE_URL)
    assert query["client_id"] == [CLIENT_ID]
    assert query["scope"] == ["openid email"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"] == [flow["state"]]
    assert query["nonce"] == [flow["nonce"]]
    assert query["redirect_uri"] == ["http://localhost:8000/logowanie/google/powrot/"]
    assert flow["verifier"] not in response["Location"]


# --- the answer from Google must be genuine and meant for this browser ----


@pytest.mark.django_db
def test_callback_without_a_flow_of_this_browser_is_refused(client, google_on):
    """Login CSRF: a code from someone else's browser must not sign in here."""
    response = client.get(
        reverse("accounts:google-callback"), {"state": "x", "code": "c"}
    )

    assert response.status_code == 400
    assert _logged_in_as(client) is None


@pytest.mark.django_db
def test_wrong_state_is_refused_and_the_flow_is_used_up(client, google_on):
    client.get(reverse("accounts:google-start"))
    flow = client.session["google_oauth"]
    google_on["token"] = _token(flow["nonce"])

    wrong = client.get(reverse("accounts:google-callback"), {"state": "x", "code": "c"})
    replay = client.get(
        reverse("accounts:google-callback"), {"state": flow["state"], "code": "c"}
    )

    assert wrong.status_code == 400
    assert replay.status_code == 400
    assert _logged_in_as(client) is None


@pytest.mark.django_db
def test_old_flow_is_refused(client, google_on):
    client.get(reverse("accounts:google-start"))
    session = client.session
    session["google_oauth"]["started"] -= google.FLOW_MAX_AGE + 1
    session.save()
    flow = client.session["google_oauth"]
    google_on["token"] = _token(flow["nonce"])

    response = client.get(
        reverse("accounts:google-callback"), {"state": flow["state"], "code": "c"}
    )

    assert response.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "someone-else"},
        {"iss": "https://evil.example.com"},
        {"exp": int(time.time()) - 3600},
        {"nonce": "replayed"},
        {"azp": "someone-else"},
        {"email_verified": False},
        {"email": None},
    ],
    ids=["audience", "issuer", "expired", "nonce", "azp", "unverified", "no-email"],
)
def test_forged_or_foreign_tokens_are_refused(client, google_on, claims):
    client.get(reverse("accounts:google-start"))
    flow = client.session["google_oauth"]
    overrides = dict(claims)
    nonce = overrides.pop("nonce", flow["nonce"])
    google_on["token"] = _token(nonce, **overrides)

    response = client.get(
        reverse("accounts:google-callback"), {"state": flow["state"], "code": "c"}
    )

    assert response.status_code == 400
    assert _logged_in_as(client) is None
    assert not User.objects.exists()


@pytest.mark.django_db
def test_token_signed_with_another_key_is_refused(client, google_on):
    response = _google(client, google_on, key=OTHER_KEY)

    assert response.status_code == 400
    assert _logged_in_as(client) is None


@pytest.mark.django_db
def test_person_who_cancels_at_google_goes_back_to_login(client, google_on):
    client.get(reverse("accounts:google-start"))

    response = client.get(
        reverse("accounts:google-callback"), {"error": "access_denied"}
    )

    assert response["Location"] == reverse("accounts:login")


# --- signing up --------------------------------------------------------------


@pytest.mark.django_db
def test_gmail_sign_up_needs_the_terms_then_starts_at_once(client, google_on):
    response = _google(client, google_on)
    assert response["Location"] == reverse("accounts:google-signup")
    assert _logged_in_as(client) is None
    assert "jan@gmail.com" in page_text(client.get(reverse("accounts:google-signup")))

    refused = client.post(reverse("accounts:google-signup"), {})
    assert refused.status_code == 200
    assert not User.objects.exists()

    _accept_terms(client)

    user = User.objects.get()
    assert _logged_in_as(client) == user
    assert user.email == "jan@gmail.com"
    assert user.email_verified_at is not None
    assert user.terms_accepted_at is not None
    assert not user.has_usable_password()
    assert user.google_account.subject == "google-sub-1"


@pytest.mark.django_db
def test_workspace_address_counts_as_run_by_google(client, google_on):
    _google(client, google_on, email="anna@biuro.pl", hd="biuro.pl")
    _accept_terms(client)

    assert _logged_in_as(client).email == "anna@biuro.pl"


@pytest.mark.django_db
def test_other_address_is_confirmed_by_email_in_the_same_browser(client, google_on):
    _google(client, google_on, email="anna@firma.pl")
    response = _accept_terms(client)

    assert "Sprawdź swoją skrzynkę" in page_text(response)
    assert not User.objects.exists()
    link = _confirm_link("anna@firma.pl")

    # Opened elsewhere (someone else's browser): refused.
    elsewhere = BrowserClient()
    assert elsewhere.post(link).status_code == 400
    assert not User.objects.exists()

    # Opening only shows a button; the click creates the account.
    assert client.get(link).status_code == 200
    assert not User.objects.exists()
    client.post(link)

    user = User.objects.get()
    assert _logged_in_as(client) == user
    assert user.email_verified_at is not None
    assert user.google_account.email == "anna@firma.pl"


# --- the same person, two ways in -----------------------------------------


@pytest.fixture
def password_user(db):
    from django.utils import timezone

    return User.objects.create_user(
        email="jan@gmail.com",
        password="s3cr3t-pass!",
        email_verified_at=timezone.now(),
    )


@pytest.mark.django_db
def test_gmail_joins_the_existing_password_account(client, google_on, password_user):
    mail.outbox.clear()

    _google(client, google_on)

    assert _logged_in_as(client) == password_user
    assert password_user.google_account.subject == "google-sub-1"
    # The password still works, and the owner is told about the new way in.
    password_user.refresh_from_db()
    assert password_user.check_password("s3cr3t-pass!")
    assert [m.subject for m in mail.outbox] == [
        "Dodano logowanie przez Google – Monituj"
    ]


@pytest.mark.django_db
def test_later_sign_ins_follow_the_google_id_not_the_address(
    client, google_on, password_user
):
    _google(client, google_on)
    client.logout()

    # Changed their Gmail address meanwhile - still their account.
    _google(client, google_on, email="jan.nowy@gmail.com")

    assert _logged_in_as(client) == password_user
    assert GoogleAccount.objects.get().email == "jan.nowy@gmail.com"


@pytest.mark.django_db
def test_other_address_joins_an_account_only_after_the_email_click(client, google_on):
    from django.utils import timezone

    user = User.objects.create_user(
        email="anna@firma.pl", password="s3cr3t-pass!", email_verified_at=timezone.now()
    )

    response = _google(client, google_on, email="anna@firma.pl")

    assert "Sprawdź swoją skrzynkę" in page_text(response)
    assert _logged_in_as(client) is None
    assert not GoogleAccount.objects.exists()
    client.post(_confirm_link("anna@firma.pl"))
    assert _logged_in_as(client) == user
    assert user.google_account.subject == "google-sub-1"


@pytest.mark.django_db
def test_unconfirmed_account_goes_to_the_mailbox_owner(client, google_on):
    """Pre-hijack: someone registers jan@gmail.com with their own password
    and never confirms it. Jan signs in with Google: the account is his, and
    the stranger's password stops working."""
    squatter = User.objects.create_user(email="jan@gmail.com", password="squat-pass-1!")

    _google(client, google_on)

    squatter.refresh_from_db()
    assert _logged_in_as(client) == squatter
    assert squatter.email_verified_at is not None
    assert not squatter.has_usable_password()


@pytest.mark.django_db
def test_account_linked_to_another_google_account_is_not_taken_over(
    client, google_on, password_user
):
    GoogleAccount.objects.create(
        user=password_user, subject="another-sub", email="jan@gmail.com"
    )

    response = _google(client, google_on)

    assert response.status_code == 400
    assert _logged_in_as(client) is None


@pytest.mark.django_db
def test_passwordless_guest_account_becomes_a_regular_one(client, google_on):
    from django.utils import timezone

    guest = User.objects.create_user(
        email="jan@gmail.com", email_verified_at=timezone.now()
    )
    GuestAccess.objects.create(user=guest)

    _google(client, google_on)

    assert _logged_in_as(client) == guest
    assert not GuestAccess.objects.filter(user=guest).exists()


@pytest.mark.django_db
def test_inactive_and_demo_accounts_cannot_be_reached(client, google_on):
    from datetime import timedelta

    from django.utils import timezone

    User.objects.create_user(email="jan@gmail.com", is_active=False)
    assert _google(client, google_on).status_code == 400

    demo = User.objects.create_user(email="demo@gmail.com")
    DemoAccount.objects.create(
        user=demo, expires_at=timezone.now() + timedelta(hours=1)
    )
    assert _google(client, google_on, email="demo@gmail.com").status_code == 400
    assert _logged_in_as(client) is None


@pytest.mark.django_db
def test_google_only_account_cannot_sign_in_with_a_blank_password(client, google_on):
    _google(client, google_on)
    _accept_terms(client)
    browser = BrowserClient()

    response = browser.post(
        reverse("accounts:login"), {"email": "jan@gmail.com", "password": ""}
    )

    assert _logged_in_as(browser) is None
    assert response.status_code in (200, 400, 401)


# --- settings ---------------------------------------------------------------


@pytest.mark.django_db
def test_connect_from_settings_with_any_google_address(
    client, google_on, password_user
):
    client.force_login(password_user)

    _google(client, google_on, start="accounts:google-connect", email="inny@gmail.com")

    assert password_user.google_account.email == "inny@gmail.com"
    assert _logged_in_as(client) == password_user


@pytest.mark.django_db
def test_google_account_of_someone_else_cannot_be_connected(
    client, google_on, password_user
):
    other = User.objects.create_user(email="other@example.com", password="x-pass-12!")
    GoogleAccount.objects.create(
        user=other, subject="google-sub-1", email="a@gmail.com"
    )
    client.force_login(password_user)

    _google(client, google_on, start="accounts:google-connect")

    assert not GoogleAccount.objects.filter(user=password_user).exists()


@pytest.mark.django_db
def test_disconnect_needs_a_password(client, google_on):
    _google(client, google_on)
    _accept_terms(client)
    user = _logged_in_as(client)

    client.post(reverse("accounts:settings"), {"form_action": "google_disconnect"})

    assert GoogleAccount.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_disconnect_with_a_password(client, google_on, password_user):
    _google(client, google_on)
    mail.outbox.clear()

    client.post(reverse("accounts:settings"), {"form_action": "google_disconnect"})

    assert not GoogleAccount.objects.exists()
    assert mail.outbox[0].subject == "Odłączono logowanie przez Google – Monituj"


@pytest.mark.django_db
def test_settings_of_a_google_only_account(client, google_on):
    _google(client, google_on)
    _accept_terms(client)

    page = page_text(client.get(reverse("accounts:settings")))

    assert 'value="set_password"' in page
    assert 'value="email"' not in page  # changing the address needs a password
    assert 'value="google_disconnect"' not in page
    assert "id_delete_current_password" not in page


@pytest.mark.django_db
def test_google_pages_are_never_indexed(client, google_on):
    response = client.get(reverse("accounts:google-start"))

    assert response["X-Robots-Tag"] == "noindex, nofollow"
