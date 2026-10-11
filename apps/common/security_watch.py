"""The alarm: an email to settings.SECURITY_EMAIL the moment something
happens that the owner must know about, whoever did it -

- an account with admin rights signs in (also when only the password was
  right and the two-step code is still to come: someone knows the password);
- the admin login is blocked after too many wrong passwords;
- an account gets admin rights, or an admin's password changes or their
  two-step verification is switched off;
- anyone touches the canary - an address that exists only in the database
  (settings.SECURITY_CANARY_EMAIL, `manage.py security_canary`): nobody can
  know it without having read the users table.

The server's own alarms (an SSH login, a changed system file - deploy/
security/) come through here too: `manage.py security_alert`. One channel,
so adding another (a phone push) is one function - _deliver.

Nothing here may break what the person was doing: every hook swallows its
own errors. The same alarm is sent once per QUIET, however often it fires.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from apps.common import throttle
from apps.common.security import get_client_ip, hash_token

logger = logging.getLogger("monituj.security")
QUIET = timedelta(minutes=10)
# What an alarm says about the person at the other end.
MAX_AGENT = 160


def enabled():
    return bool(settings.SECURITY_ALERTS and settings.SECURITY_EMAIL)


def _deliver(subject, body):
    EmailMessage(
        subject=f"{settings.EMAIL_SUBJECT_PREFIX}ALARM: {subject}",
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[settings.SECURITY_EMAIL],
    ).send(fail_silently=False)


def alert(subject, lines, key=None, quiet=QUIET):
    """Sends the alarm unless the same one (key) went out within `quiet`.
    -> whether it was sent."""
    if not enabled():
        return False
    try:
        throttle_key = "security-alert:" + hash_token(key or subject)[:48]
        if throttle.is_limited(throttle_key, 1, quiet):
            return False
        throttle.record(throttle_key)
        body = "\n".join(
            [
                f"Czas: {timezone.localtime():%Y-%m-%d %H:%M:%S} "
                f"({settings.TIME_ZONE})",
                *lines,
                "",
                "Jeśli to nie Ty ani nikt z zespołu - potraktuj to jak włamanie: "
                "zmień hasła, sprawdź raport bezpieczeństwa i logi serwera "
                "(README, „Monitoring bezpieczeństwa”).",
            ]
        )
        _deliver(subject, body)
        logger.warning("security alert sent: %s", subject)
        return True
    except Exception:
        logger.exception("security alert failed: %s", subject)
        return False


def _who(request):
    if request is None:
        return ["Adres IP: brak (zadanie w tle albo konsola)"]
    agent = request.META.get("HTTP_USER_AGENT", "")[:MAX_AGENT] or "brak"
    return [f"Adres IP: {get_client_ip(request)}", f"Przeglądarka: {agent}"]


# --- sign-ins of accounts with admin rights ---------------------------------------


def on_login(sender, request, user, **kwargs):
    try:
        if not user.is_staff:
            return
        ip = get_client_ip(request) if request is not None else ""
        alert(
            f"logowanie administratora {user.email}",
            [
                f"Konto: {user.email}"
                + (" (superużytkownik)" if user.is_superuser else ""),
                *_who(request),
                "Hasło było poprawne. Przy włączonej weryfikacji dwuetapowej ta "
                "wiadomość przychodzi już po samym haśle - zanim padnie kod.",
            ],
            key=f"staff-login:{user.pk}:{ip}",
        )
    except Exception:
        logger.exception("security: staff login hook failed")


def admin_login_blocked(request, login):
    alert(
        "panel administratora zablokowany po nieudanych próbach",
        [
            f"Podany login: {login or 'brak'}",
            *_who(request),
            "Ktoś wielokrotnie podał błędne hasło do panelu administratora. "
            "Kolejne próby z tego adresu i na ten login są wstrzymane na 15 minut.",
        ],
        key=f"admin-blocked:{get_client_ip(request)}",
        quiet=timedelta(minutes=15),
    )


# --- admin rights given, an admin's password or two-step verification changed ----


def remember_rights(sender, instance, **kwargs):
    """pre_save: what the account could do before this save."""
    try:
        before = None
        if instance.pk:
            before = (
                sender.objects.filter(pk=instance.pk)
                .values("is_staff", "is_superuser", "password")
                .first()
            )
        instance._rights_before = before
    except Exception:
        instance._rights_before = None


def rights_changed(sender, instance, created, **kwargs):
    try:
        before = getattr(instance, "_rights_before", None) or {}
        was_staff = bool(before.get("is_staff"))
        was_super = bool(before.get("is_superuser"))
        if (instance.is_staff and not was_staff) or (
            instance.is_superuser and not was_super
        ):
            alert(
                f"konto {instance.email} dostało uprawnienia administratora",
                [
                    f"Konto: {instance.email} (id {instance.pk})"
                    + (" - nowe konto" if created else ""),
                    f"Dostęp do panelu administratora: "
                    f"{'tak' if instance.is_staff else 'nie'}",
                    f"Superużytkownik: {'tak' if instance.is_superuser else 'nie'}",
                    "Takie konto może zmienić każde inne konto i czytać dane.",
                ],
                key=f"staff-granted:{instance.pk}",
            )
        elif (
            instance.is_staff and before and before.get("password") != instance.password
        ):
            alert(
                f"zmieniono hasło administratora {instance.email}",
                [f"Konto: {instance.email} (id {instance.pk})"],
                key=f"staff-password:{instance.pk}",
            )
    except Exception:
        logger.exception("security: rights hook failed")


def on_audit(sender, instance, created, **kwargs):
    """Entries of the audit log that are alarms in themselves."""
    try:
        if not created:
            return
        actor = instance.actor
        if (
            instance.event == "TWO_FACTOR_DISABLED"
            and actor is not None
            and actor.is_staff
        ):
            alert(
                f"wyłączono weryfikację dwuetapową administratora {actor.email}",
                [
                    f"Konto: {actor.email} (id {actor.pk})",
                    f"Adres IP: {instance.ip_address or 'brak'}",
                    "Od teraz do panelu administratora wystarcza samo hasło.",
                ],
                key=f"staff-2fa-off:{actor.pk}",
            )
    except Exception:
        logger.exception("security: audit hook failed")


# --- the canary ---------------------------------------------------------------------


def is_canary(email):
    canary = (settings.SECURITY_CANARY_EMAIL or "").strip().lower()
    return bool(canary) and (email or "").strip().lower() == canary


def canary_touched(email, what, request=None):
    """Someone used the address that exists only in the database."""
    try:
        if not is_canary(email):
            return False
        return alert(
            "ktoś użył adresu-przynęty z bazy danych",
            [
                f"Co zrobiono: {what}",
                *_who(request),
                "Tego adresu nie ma nigdzie poza bazą Monituj. Ktoś, kto go zna, "
                "najpewniej czytał tabelę użytkowników - to mocny sygnał wycieku "
                "bazy danych.",
            ],
            key=f"canary:{what}",
            quiet=timedelta(minutes=30),
        )
    except Exception:
        logger.exception("security: canary hook failed")
        return False
