"""Two-step verification: turning it on, every way of signing in asking for
the code, backup codes, remembered devices, turning it off and the panel's
hint."""

import re
import time
from datetime import timedelta

import pyotp
import pytest
from django.core import mail
from django.core.management import call_command
from django.test import Client as Browser
from django.urls import reverse
from django.utils import timezone

from apps.accounts import two_factor
from apps.accounts.models import GuestAccess, TwoFactor, User
from apps.accounts.services import GuestAccessService
from apps.audit.models import AuditEvent, AuditLog
from apps.documents import encryption
from tests.conftest import page_text
from tests.test_google_login import _google, google_on  # noqa: F401 - fixture

PASSWORD = "s3cr3t-pass!"
SETUP_URL = "/ustawienia/weryfikacja-dwuetapowa/"
CODE_URL = "/logowanie/kod/"


@pytest.fixture
def owner(db):
    return User.objects.create_user(
        email="jan@gmail.com", password=PASSWORD, email_verified_at=timezone.now()
    )


def _turn_on(browser, user):
    """Goes through Settings like a person would. -> (secret, backup codes)."""
    browser.force_login(user)
    browser.post(SETUP_URL, {"form_action": "start", "current_password": PASSWORD})
    secret = browser.session[two_factor.SETUP_KEY]["s"]
    browser.post(
        SETUP_URL, {"form_action": "confirm", "code": pyotp.TOTP(secret).now()}
    )
    codes = _shown_codes(browser.get(SETUP_URL))
    browser.logout()
    return secret, codes


def _shown_codes(response):
    """The backup codes on the page (shown once, after turning it on)."""
    page = page_text(response)
    if 'class="backup-codes"' not in page:
        return []
    block = page.split('class="backup-codes"')[1].split("</ul>")[0]
    return re.findall(r"<code>([^<]+)</code>", block)


def _next_code(secret, steps=1):
    # The code of a later 30-second step: the current one was used already.
    return pyotp.TOTP(secret).at(time.time() + 30 * steps)


def _password_login(browser, **extra):
    return browser.post(
        reverse("accounts:login"),
        {"email": "jan@gmail.com", "password": PASSWORD},
        **extra,
    )


def _logged_in(browser):
    return bool(browser.session.get("_auth_user_id"))


# --- turning it on -----------------------------------------------------------


@pytest.mark.django_db
def test_turning_on_needs_the_password_and_a_code_from_the_app(client, owner):
    client.force_login(owner)
    assert "Wyłączona" in page_text(client.get(SETUP_URL))

    wrong = client.post(SETUP_URL, {"form_action": "start", "current_password": "x"})
    assert "Nieprawidłowe hasło" in page_text(wrong)
    assert two_factor.SETUP_KEY not in client.session

    client.post(SETUP_URL, {"form_action": "start", "current_password": PASSWORD})
    page = page_text(client.get(SETUP_URL))
    assert "<svg" in page and "zeskanuj" in page.lower()
    secret = client.session[two_factor.SETUP_KEY]["s"]

    bad = client.post(SETUP_URL, {"form_action": "confirm", "code": "000000"})
    assert "Nieprawidłowy kod" in page_text(bad)
    assert not TwoFactor.objects.exists()

    mail.outbox.clear()
    client.post(SETUP_URL, {"form_action": "confirm", "code": pyotp.TOTP(secret).now()})

    assert len(_shown_codes(client.get(SETUP_URL))) == 10
    # Shown once only.
    assert _shown_codes(client.get(SETUP_URL)) == []
    row = TwoFactor.objects.get(user=owner)
    assert row.secret_key_id and secret not in row.secret
    assert len(row.backup_codes) == 10
    assert [m.subject for m in mail.outbox] == [
        "Włączono weryfikację dwuetapową - Monituj"
    ]
    assert AuditLog.objects.filter(event=AuditEvent.TWO_FACTOR_ENABLED).exists()


@pytest.mark.django_db
def test_guest_and_demo_accounts_cannot_turn_it_on(client, owner):
    GuestAccess.objects.create(user=owner)
    client.force_login(owner)

    response = client.get(SETUP_URL)

    assert response.status_code == 302
    assert response.url == reverse("accounts:settings")


# --- signing in --------------------------------------------------------------


@pytest.mark.django_db
def test_password_alone_no_longer_logs_in(owner):
    secret, _ = _turn_on(Browser(), owner)
    browser = Browser()

    response = _password_login(browser)

    assert response.status_code == 302 and response.url == CODE_URL
    assert not _logged_in(browser)
    assert browser.get(reverse("accounts:panel")).status_code == 302

    wrong = browser.post(CODE_URL, {"code": "123456"})
    assert "Nieprawidłowy kod" in page_text(wrong)
    assert not _logged_in(browser)

    done = browser.post(CODE_URL, {"code": _next_code(secret)})

    assert done.status_code == 302 and done.url == reverse("accounts:panel")
    assert _logged_in(browser)
    login = AuditLog.objects.filter(event=AuditEvent.USER_LOGIN).latest("created_at")
    assert login.metadata == {"method": "password", "two_factor": "app"}


@pytest.mark.django_db
def test_a_code_from_the_app_works_only_once(owner):
    secret, _ = _turn_on(Browser(), owner)
    code = _next_code(secret)
    first = Browser()
    _password_login(first)
    first.post(CODE_URL, {"code": code})
    assert _logged_in(first)

    second = Browser()
    _password_login(second)
    replay = second.post(CODE_URL, {"code": code})

    assert "Nieprawidłowy kod" in page_text(replay)
    assert not _logged_in(second)


@pytest.mark.django_db
def test_backup_code_works_once_and_the_owner_is_told(owner):
    _, codes = _turn_on(Browser(), owner)
    mail.outbox.clear()
    browser = Browser()
    _password_login(browser)

    browser.post(CODE_URL, {"code": codes[0].upper().replace("-", " ")})

    assert _logged_in(browser)
    assert two_factor.remaining_backup_codes(owner) == 9
    assert [m.subject for m in mail.outbox] == [
        "Zalogowano się kodem zapasowym - Monituj"
    ]
    again = Browser()
    _password_login(again)
    assert "Nieprawidłowy kod" in page_text(again.post(CODE_URL, {"code": codes[0]}))


@pytest.mark.django_db
def test_wrong_codes_are_limited(owner):
    secret, _ = _turn_on(Browser(), owner)
    browser = Browser()
    _password_login(browser)
    for _ in range(two_factor.FAILURES_PER_ACCOUNT):
        browser.post(CODE_URL, {"code": "000000"})

    blocked = browser.post(CODE_URL, {"code": _next_code(secret)})

    assert "Zbyt wiele błędnych kodów" in page_text(blocked)
    assert not _logged_in(browser)


@pytest.mark.django_db
def test_the_code_page_needs_the_first_step_first(client, owner):
    _turn_on(Browser(), owner)

    assert client.get(CODE_URL).url == reverse("accounts:login")

    _password_login(client)
    session = client.session
    pending = session[two_factor.PENDING_KEY]
    pending["t"] -= two_factor.PENDING_MAX_AGE + 1
    session[two_factor.PENDING_KEY] = pending
    session.save()
    assert client.get(CODE_URL).url == reverse("accounts:login")


@pytest.mark.django_db
def test_remembered_device_skips_the_code_until_the_password_changes(owner):
    secret, _ = _turn_on(Browser(), owner)
    browser = Browser()
    _password_login(browser)
    browser.post(CODE_URL, {"code": _next_code(secret), "remember": "on"})
    assert two_factor.DEVICE_COOKIE in browser.cookies
    browser.post(reverse("accounts:logout"))

    again = _password_login(browser)
    assert again.url == reverse("accounts:panel") and _logged_in(browser)
    browser.post(reverse("accounts:logout"))

    owner.set_password(PASSWORD)  # Same text, new hash: a password change.
    owner.save()
    assert _password_login(browser).url == CODE_URL


@pytest.mark.django_db
def test_another_browser_is_not_remembered(owner):
    secret, _ = _turn_on(Browser(), owner)
    remembered = Browser()
    _password_login(remembered)
    remembered.post(CODE_URL, {"code": _next_code(secret), "remember": "on"})

    stranger = Browser()
    stranger.cookies[two_factor.DEVICE_COOKIE] = "forged-value"

    assert _password_login(stranger).url == CODE_URL


@pytest.mark.django_db
def test_google_sign_in_asks_for_the_code_too(client, google_on, owner):  # noqa: F811
    secret, _ = _turn_on(Browser(), owner)
    _google(client, google_on)  # Links Google to the account (Gmail address).
    client.logout()

    response = _google(client, google_on)

    assert response.url == CODE_URL
    assert not _logged_in(client)
    client.post(CODE_URL, {"code": _next_code(secret)})
    assert _logged_in(client)
    login = AuditLog.objects.filter(event=AuditEvent.USER_LOGIN).latest("created_at")
    assert login.metadata == {"method": "google", "two_factor": "app"}
    assert owner.google_account.last_login_at is not None


@pytest.mark.django_db
def test_admin_login_asks_for_the_code_before_the_admin_opens(db):
    root = User.objects.create_superuser(email="root@example.com", password=PASSWORD)
    secret, _ = _turn_on(Browser(), root)
    browser = Browser()

    response = browser.post(
        "/admin/login/",
        {"username": "root@example.com", "password": PASSWORD, "next": "/admin/"},
    )

    assert response.url == CODE_URL
    assert not _logged_in(browser)
    done = browser.post(CODE_URL, {"code": _next_code(secret)})
    assert done.url == "/admin/"
    assert browser.get("/admin/").status_code == 200


@pytest.mark.django_db
def test_mailbox_links_never_skip_the_code(rf, owner):
    _turn_on(Browser(), owner)
    request = rf.get("/")
    from django.contrib.sessions.backends.db import SessionStore

    request.session = SessionStore()

    GuestAccessService.login(request, owner)

    assert "_auth_user_id" not in request.session


# --- managing it -------------------------------------------------------------


@pytest.mark.django_db
def test_turning_off_needs_the_password_and_a_code(client, owner):
    secret, _ = _turn_on(Browser(), owner)
    client.force_login(owner)
    client.cookies[two_factor.DEVICE_COOKIE] = "anything"

    refused = client.post(
        SETUP_URL,
        {"form_action": "disable", "current_password": "x", "code": _next_code(secret)},
    )
    assert "Nieprawidłowe hasło" in page_text(refused)
    assert two_factor.is_enabled(owner)

    mail.outbox.clear()
    response = client.post(
        SETUP_URL,
        {
            "form_action": "disable",
            "current_password": PASSWORD,
            "code": _next_code(secret),
        },
    )

    assert response.url == reverse("accounts:settings")
    assert not two_factor.is_enabled(owner)
    assert response.cookies[two_factor.DEVICE_COOKIE].value == ""
    assert [m.subject for m in mail.outbox] == [
        "Wyłączono weryfikację dwuetapową - Monituj"
    ]


@pytest.mark.django_db
def test_new_backup_codes_replace_the_old_ones(client, owner):
    secret, old_codes = _turn_on(Browser(), owner)
    client.force_login(owner)

    client.post(
        SETUP_URL,
        {
            "form_action": "codes",
            "current_password": PASSWORD,
            "code": _next_code(secret),
        },
    )

    new_codes = _shown_codes(client.get(SETUP_URL))
    assert len(new_codes) == 10 and old_codes[1] not in new_codes
    browser = Browser()
    _password_login(browser)
    assert "Nieprawidłowy kod" in page_text(
        browser.post(CODE_URL, {"code": old_codes[1]})
    )


@pytest.mark.django_db
def test_team_can_turn_it_off_for_someone_who_lost_the_phone(client, owner):
    _turn_on(Browser(), owner)
    root = User.objects.create_superuser(email="root@example.com", password=PASSWORD)
    client.force_login(root)
    mail.outbox.clear()

    client.post(
        reverse("admin:accounts_user_changelist"),
        {"action": "disable_two_factor", "_selected_action": [owner.pk]},
    )

    assert not two_factor.is_enabled(owner)
    [message] = mail.outbox
    assert message.to == [owner.email]
    assert "Na Twoją prośbę" in message.body.replace("\xa0", " ")


@pytest.mark.django_db
def test_rotating_the_master_key_re_encrypts_the_secret(settings, owner):
    secret, _ = _turn_on(Browser(), owner)
    old_key = settings.DOCUMENTS_ENCRYPTION_KEY
    settings.DOCUMENTS_ENCRYPTION_KEY = encryption.generate_key()
    settings.DOCUMENTS_ENCRYPTION_OLD_KEYS = [old_key]

    call_command("rewrap_document_keys")

    settings.DOCUMENTS_ENCRYPTION_OLD_KEYS = []
    row = TwoFactor.objects.get(user=owner)
    assert row.secret_key_id == encryption.current_key_id()
    assert two_factor._secret(row) == secret


# --- the panel's hint --------------------------------------------------------


@pytest.mark.django_db
def test_the_hint_waits_a_week_and_goes_away_for_90_days(client, owner):
    client.force_login(owner)
    hint = "Chroń konto kodem z telefonu"
    assert hint not in page_text(client.get(reverse("accounts:panel")))

    User.objects.filter(pk=owner.pk).update(
        date_joined=timezone.now() - timedelta(days=8)
    )
    assert hint in page_text(client.get(reverse("accounts:panel")))

    client.post(reverse("accounts:security-hint-hide"))

    assert hint not in page_text(client.get(reverse("accounts:panel")))
    owner.refresh_from_db()
    assert owner.security_hint_hidden_until == timezone.localdate() + timedelta(days=90)


@pytest.mark.django_db
def test_no_hint_once_it_is_on(client, owner):
    _turn_on(Browser(), owner)
    User.objects.filter(pk=owner.pk).update(
        date_joined=timezone.now() - timedelta(days=30)
    )
    client.force_login(owner)

    assert "Chroń konto kodem z telefonu" not in page_text(
        client.get(reverse("accounts:panel"))
    )
