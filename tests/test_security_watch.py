"""The alarm (apps/common/security_watch.py) and the daily security report
(security_digest.py): the owner hears when an admin signs in, when admin
rights are given, when the canary is touched - and gets the day's trail by
email every morning."""

import io

import pytest
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.clients.models import Client
from apps.common import security_digest, security_watch
from apps.common.tasks import send_security_digest_fallback

CANARY = "archiwum.k7q2@example.com"
PASSWORD = "Bardzo-Tajne-Haslo-91"


@pytest.fixture(autouse=True)
def _alarms_on(settings):
    settings.SECURITY_ALERTS = True
    settings.SECURITY_EMAIL = "alarm@example.com"
    settings.SECURITY_CANARY_EMAIL = CANARY


@pytest.fixture
def admin_account(db):
    return User.objects.create_superuser(email="szef@example.com", password=PASSWORD)


def _alarms(mailoutbox):
    return [m for m in mailoutbox if "ALARM" in m.subject]


# --- admins -------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_signing_in_raises_the_alarm_once(client, admin_account, mailoutbox):
    mailoutbox.clear()  # creating the superuser was an alarm of its own

    for _ in range(2):
        client.post(
            reverse("admin:login"),
            {"username": admin_account.email, "password": PASSWORD},
        )

    alarms = _alarms(mailoutbox)
    assert len(alarms) == 1  # the same sign-in again within minutes: one alarm
    assert alarms[0].to == ["alarm@example.com"]
    assert "logowanie administratora szef@example.com" in alarms[0].subject
    assert "Adres IP:" in alarms[0].body


@pytest.mark.django_db
def test_ordinary_sign_in_is_no_alarm(client, user, mailoutbox):
    client.force_login(user)
    client.post(
        reverse("accounts:login"), {"email": user.email, "password": "whatever"}
    )

    assert _alarms(mailoutbox) == []


@pytest.mark.django_db
def test_admin_rights_given_and_admin_password_changed(user, mailoutbox):
    user.is_staff = True
    user.save()
    assert "dostało uprawnienia administratora" in _alarms(mailoutbox)[-1].subject

    user.set_password("Nowe-Haslo-Admina-77")
    user.save()
    assert "zmieniono hasło administratora" in _alarms(mailoutbox)[-1].subject
    # An ordinary account changing its password is nobody's alarm.
    other = User.objects.create_user(email="zwykly@example.com", password="x")
    count = len(_alarms(mailoutbox))
    other.set_password("y")
    other.save()
    assert len(_alarms(mailoutbox)) == count


@pytest.mark.django_db
def test_new_superuser_is_an_alarm(mailoutbox):
    User.objects.create_superuser(email="nowy@example.com", password=PASSWORD)

    alarm = _alarms(mailoutbox)[-1]
    assert "nowy@example.com dostało uprawnienia administratora" in alarm.subject
    assert "nowe konto" in alarm.body


@pytest.mark.django_db
def test_admin_switching_off_two_step_verification(admin_account, user, mailoutbox):
    mailoutbox.clear()

    AuditService.log(AuditEvent.TWO_FACTOR_DISABLED, actor=user, target=user)
    assert _alarms(mailoutbox) == []
    AuditService.log(
        AuditEvent.TWO_FACTOR_DISABLED, actor=admin_account, target=admin_account
    )

    assert "wyłączono weryfikację dwuetapową" in _alarms(mailoutbox)[-1].subject


@pytest.mark.django_db
def test_blocked_admin_login_is_an_alarm(client, admin_account, mailoutbox):
    mailoutbox.clear()

    for _ in range(7):
        response = client.post(
            reverse("admin:login"),
            {"username": admin_account.email, "password": "zle-haslo"},
        )

    assert response.status_code == 429
    blocked = [m for m in _alarms(mailoutbox) if "zablokowany" in m.subject]
    assert len(blocked) == 1


# --- the canary ---------------------------------------------------------------------


@pytest.mark.django_db
def test_canary_is_planted_inactive_and_never_mailed(mailoutbox):
    out = io.StringIO()
    call_command("security_canary", stdout=out)
    call_command("security_canary", stdout=out)  # again: still one

    canary = User.objects.get(email=CANARY)
    assert not canary.is_active and not canary.has_usable_password()
    assert not canary.is_email_verified and not canary.is_staff
    assert Client.objects.filter(owner=canary, email=CANARY).count() == 1
    assert mailoutbox == []


@pytest.mark.django_db
def test_canary_refuses_a_real_account(settings, user):
    settings.SECURITY_CANARY_EMAIL = user.email

    with pytest.raises(CommandError):
        call_command("security_canary")


@pytest.mark.django_db
def test_signing_in_with_the_canary_raises_the_alarm(client, mailoutbox):
    call_command("security_canary", stdout=io.StringIO())

    client.post(reverse("accounts:login"), {"email": CANARY, "password": "zgaduje"})

    alarm = _alarms(mailoutbox)[-1]
    assert "adresu-przynęty" in alarm.subject
    assert "próba logowania" in alarm.body


@pytest.mark.django_db
def test_password_reset_for_the_canary_alarms_and_sends_it_nothing(client, mailoutbox):
    call_command("security_canary", stdout=io.StringIO())

    client.post(reverse("accounts:password-reset-request"), {"email": CANARY})

    assert [m.to for m in mailoutbox] == [["alarm@example.com"]]
    assert "reset hasła" in mailoutbox[0].body


# --- from the server ----------------------------------------------------------------


@pytest.mark.django_db
def test_server_alarm_command(mailoutbox, monkeypatch):
    monkeypatch.setattr(
        "sys.stdin", io.StringIO("Użytkownik: deploy\nZ adresu: 1.2.3.4\n")
    )

    call_command(
        "security_alert", "logowanie SSH: deploy z 1.2.3.4", stdout=io.StringIO()
    )

    assert "logowanie SSH: deploy z 1.2.3.4" in mailoutbox[0].subject
    assert "Źródło: serwer" in mailoutbox[0].body
    assert "Z adresu: 1.2.3.4" in mailoutbox[0].body


@pytest.mark.django_db
def test_nothing_when_switched_off(settings, admin_account, client, mailoutbox):
    mailoutbox.clear()
    settings.SECURITY_ALERTS = False

    client.post(
        reverse("admin:login"), {"username": admin_account.email, "password": PASSWORD}
    )

    assert not security_watch.alert("cokolwiek", [])
    assert mailoutbox == []


# --- the daily report ---------------------------------------------------------------


@pytest.mark.django_db
def test_report_lists_what_needs_a_look_and_attaches_the_log(
    client, admin_account, user, rf
):
    request = rf.post("/logowanie/", REMOTE_ADDR="203.0.113.9")
    for _ in range(security_digest.MANY_FAILED_FROM_ONE_IP):
        AuditService.log(
            AuditEvent.USER_LOGIN_FAILED, request=request, metadata={"email": "a@b.pl"}
        )
    AuditService.log(
        AuditEvent.USER_LOGIN_FAILED, request=request, metadata={"email": CANARY}
    )
    client.post(
        reverse("admin:login"), {"username": admin_account.email, "password": PASSWORD}
    )
    LogEntry.objects.create(
        user=admin_account,
        content_type=ContentType.objects.get_for_model(User),
        object_id=str(user.pk),
        object_repr=user.email,
        action_flag=CHANGE,
    )

    subject, body, attachments = security_digest.build(
        host_report="Serwer: vps\n! logowanie SSH na konto root\nDysk: zajęte 40%"
    )

    assert "do sprawdzenia" in subject
    top = body.split("LOGOWANIA")[0]
    assert "nieudanych logowań z jednego adresu: 203.0.113.9" in top
    assert "logowanie administratora szef@example.com" in top
    assert "adres-przynęta" in top
    assert "serwer: logowanie SSH na konto root" in top
    assert "nowe konto z uprawnieniami administratora: szef@example.com" in top
    assert "szef@example.com (superużytkownik)" in body
    assert f"Zmiana: {user.email}" in body or user.email in body
    assert "Dysk: zajęte 40%" in body
    name, content, mimetype = attachments[0]
    assert name.endswith(".csv") and mimetype == "text/csv"
    assert "USER_LOGIN_FAILED" in content and "203.0.113.9" in content


@pytest.mark.django_db
def test_quiet_day_says_so_but_misses_the_server_part():
    subject, body, _ = security_digest.build(host_report="Serwer: vps\nDysk: 12%")
    assert subject.endswith("spokojnie")
    assert "WYMAGA UWAGI\n- nic" in body

    subject, body, _ = security_digest.build()
    assert "raport z serwera nie dotarł" in body


@pytest.mark.django_db
def test_report_command_sends_it_and_the_fallback_stays_quiet(mailoutbox, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("Serwer: vps\n"))

    call_command("security_digest", "--host-report", "-", stdout=io.StringIO())

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["alarm@example.com"]
    assert "Raport bezpieczeństwa" in mailoutbox[0].subject
    assert mailoutbox[0].attachments
    assert send_security_digest_fallback() is False  # it went out already
    assert len(mailoutbox) == 1


@pytest.mark.django_db
def test_fallback_sends_the_sites_part_when_the_server_didnt(mailoutbox):
    assert send_security_digest_fallback() is True

    assert "raport z serwera nie dotarł" in mailoutbox[0].body
    assert send_security_digest_fallback() is False
