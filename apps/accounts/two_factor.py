"""Two-step verification: a code from an authenticator app (TOTP, RFC 6238).

- Turned on in Settings: the secret is shown as a QR code and kept in the
  session until the first code confirms it; then it is stored encrypted
  with the master key. Ten one-time backup codes are shown once.
- Every way into an account that has it on - password, Google, the admin -
  stops after the first step: the person is held in the session as
  "pending" and gets in only with a code (challenge / complete).
- "Zapamiętaj to urządzenie": a signed cookie for 30 days. It stops working
  when the password changes or two-step verification is turned off.
- A code from the app works once, one 30-second step either side of now is
  accepted. Wrong codes are limited per account and per address.
- Lost phone and codes: the team turns it off in the admin after checking
  who is asking (admin_disable).
"""

import secrets
import time
from datetime import timedelta

import pyotp
import segno
from django.conf import settings
from django.contrib.auth import login as django_login
from django.core import signing
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.safestring import mark_safe

from apps.accounts.models import GoogleAccount, TwoFactor, User, is_guest_account
from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.common import throttle
from apps.common.exceptions import RateLimitedAppError, ValidationAppError
from apps.common.security import hash_token
from apps.demo.models import is_demo_user
from apps.documents import encryption
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService

ISSUER = "Monituj"
SECRET_AAD = b"monituj-two-factor-secret"
PENDING_KEY = "two_factor_pending"
PENDING_MAX_AGE = 10 * 60
SETUP_KEY = "two_factor_setup"
SETUP_MAX_AGE = 15 * 60
NEW_CODES_KEY = "two_factor_new_codes"
DEVICE_COOKIE = "monituj_2fa"
DEVICE_SALT = "two-factor-device"
DEVICE_MAX_AGE = 30 * 24 * 3600
BACKUP_CODE_COUNT = 10
BACKUP_CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
FAILURES_PER_ACCOUNT = 5
FAILURES_PER_IP = 20
FAILURE_WINDOW = timedelta(minutes=15)
PASSWORD_FAILURES = 5
# The panel's hint: for accounts at least this old, or once files came in.
HINT_AFTER = timedelta(days=7)
HINT_SNOOZE = timedelta(days=90)

EXPIRED_MESSAGE = "Minęło zbyt dużo czasu. Zaloguj się ponownie."
SETUP_EXPIRED_MESSAGE = "Minęło zbyt dużo czasu. Zacznij włączanie od nowa."
INVALID_CODE_MESSAGE = (
    "Nieprawidłowy kod. Wpisz aktualny kod z aplikacji (zmienia się co 30 "
    "sekund) albo jeden z kodów zapasowych."
)
TOO_MANY_MESSAGE = "Zbyt wiele błędnych kodów. Spróbuj ponownie za 15 minut."


# --- who can use it ----------------------------------------------------------


def can_use(user):
    """Regular accounts only: guest accounts log in with a link from their
    mailbox, demo accounts are shared."""
    return (
        user.is_authenticated
        and user.is_active
        and not is_guest_account(user)
        and not is_demo_user(user)
    )


def is_enabled(user):
    return TwoFactor.objects.filter(user_id=user.pk).exists()


def settings_for(user):
    return TwoFactor.objects.filter(user_id=user.pk).first()


# --- codes -------------------------------------------------------------------


def _secret(two_factor):
    return encryption.unseal(
        two_factor.secret, two_factor.secret_key_id, SECRET_AAD
    ).decode()


def _normalize(code):
    return "".join((code or "").split()).replace("-", "").lower()


def _matching_step(secret, code, now=None):
    """The 30-second step the app code belongs to (now, or one step either
    side for a clock that is a little off), or None."""
    if not (len(code) == 6 and code.isdigit()):
        return None
    totp = pyotp.TOTP(secret)
    step = int((now or time.time()) // totp.interval)
    for candidate in (step - 1, step, step + 1):
        if constant_time_compare(totp.generate_otp(candidate), code):
            return candidate
    return None


def _use_code(user, code):
    """ "app" or "backup" - what the code was - or None. A matching code is
    used up: an app code's step can't be used again, a backup code is
    removed."""
    code = _normalize(code)
    if not code:
        return None
    with transaction.atomic():
        two_factor = TwoFactor.objects.select_for_update().filter(user=user).first()
        if two_factor is None:
            return None
        step = _matching_step(_secret(two_factor), code)
        if step is not None:
            if step <= two_factor.last_step:
                return None
            two_factor.last_step = step
            two_factor.save(update_fields=["last_step", "updated_at"])
            return "app"
        digest = hash_token(code)
        if digest in two_factor.backup_codes:
            two_factor.backup_codes = [
                c for c in two_factor.backup_codes if c != digest
            ]
            two_factor.save(update_fields=["backup_codes", "updated_at"])
            return "backup"
    return None


def _check_limits(request, user):
    if throttle.is_limited(
        f"2fa:{user.pk}", FAILURES_PER_ACCOUNT, FAILURE_WINDOW
    ) or throttle.is_limited(
        throttle.ip_key("2fa-ip", request), FAILURES_PER_IP, FAILURE_WINDOW
    ):
        raise RateLimitedAppError(TOO_MANY_MESSAGE, code="TWO_FACTOR_LIMIT")


def _record_failure(request, user):
    throttle.record(f"2fa:{user.pk}")
    throttle.record(throttle.ip_key("2fa-ip", request))
    AuditService.log(
        AuditEvent.TWO_FACTOR_FAILED, actor=user, target=user, request=request
    )


def verify(request, user, code):
    """Checks a code (app or backup) within the limits. -> "app"/"backup"."""
    _check_limits(request, user)
    kind = _use_code(user, code)
    if kind is None:
        _record_failure(request, user)
        raise ValidationAppError(INVALID_CODE_MESSAGE, code="INVALID_CODE")
    throttle.clear(f"2fa:{user.pk}")
    return kind


def _new_backup_codes():
    codes = [
        "".join(secrets.choice(BACKUP_CODE_ALPHABET) for _ in range(10))
        for _ in range(BACKUP_CODE_COUNT)
    ]
    return [f"{code[:5]}-{code[5:]}" for code in codes], [
        hash_token(code) for code in codes
    ]


def check_password(request, user, password):
    """Turning it on or off and new backup codes need the password - a
    stolen session alone must not change them. Accounts without a password
    (Google only) have nothing to check."""
    if not user.has_usable_password():
        return
    key = f"2fa-password:{user.pk}"
    throttle.consume(
        key,
        PASSWORD_FAILURES,
        FAILURE_WINDOW,
        "Zbyt wiele prób. Spróbuj ponownie za 15 minut.",
        code="REAUTH_LIMIT_REACHED",
    )
    if not user.check_password(password or ""):
        raise ValidationAppError(
            "Nieprawidłowe hasło.", code="INVALID_CURRENT_PASSWORD"
        )
    throttle.clear(key)


# --- signing in --------------------------------------------------------------


def _password_marker(user):
    # Changes with the password: a remembered device or a half-finished
    # sign-in from before a password change no longer counts.
    return salted_hmac(
        "two-factor-password", user.password, algorithm="sha256"
    ).hexdigest()[:16]


def _remembered(request, user, two_factor):
    raw = request.COOKIES.get(DEVICE_COOKIE)
    if not raw:
        return False
    try:
        data = signing.loads(raw, salt=DEVICE_SALT, max_age=DEVICE_MAX_AGE)
    except signing.BadSignature:
        return False
    return (
        data.get("u") == user.pk
        and constant_time_compare(data.get("n", ""), two_factor.device_nonce)
        and constant_time_compare(data.get("p", ""), _password_marker(user))
    )


def needs_code(request, user):
    two_factor = settings_for(user)
    return two_factor is not None and not _remembered(request, user, two_factor)


def hold(request, user, backend, method, next_url=""):
    """The first step is done: remembers who is signing in until the code."""
    request.session.cycle_key()
    request.session[PENDING_KEY] = {
        "u": user.pk,
        "b": backend,
        "m": method,
        "n": next_url,
        "p": _password_marker(user),
        "t": int(time.time()),
    }


def challenge(request, user, backend, method, next_url=""):
    """True when the account needs a code first - the person is then held
    (not logged in) and should be sent to pending_url()."""
    if not needs_code(request, user):
        return False
    hold(request, user, backend, method, next_url)
    return True


def pending_user(request):
    data = request.session.get(PENDING_KEY)
    if not data or time.time() - data["t"] > PENDING_MAX_AGE:
        request.session.pop(PENDING_KEY, None)
        return None
    user = User.objects.filter(pk=data["u"], is_active=True).first()
    if (
        user is None
        or not is_enabled(user)
        or not constant_time_compare(data["p"], _password_marker(user))
    ):
        request.session.pop(PENDING_KEY, None)
        return None
    return user


def pending_url(request):
    """The code page when someone is held there, else None."""
    if request.session.get(PENDING_KEY) and pending_user(request):
        return reverse("accounts:two-factor-login")
    return None


def complete(request, code):
    """The second step. -> (user, "app"/"backup", where they were going)."""
    user = pending_user(request)
    if user is None:
        raise ValidationAppError(EXPIRED_MESSAGE, code="TWO_FACTOR_EXPIRED")
    data = request.session[PENDING_KEY]
    kind = verify(request, user, code)
    request.session.pop(PENDING_KEY, None)
    django_login(request, user, backend=data["b"])
    if data["m"] == "google":
        GoogleAccount.objects.filter(user=user).update(last_login_at=timezone.now())
    AuditService.log(
        AuditEvent.USER_LOGIN,
        actor=user,
        target=user,
        request=request,
        metadata={"method": data["m"], "two_factor": kind},
    )
    if kind == "backup":
        EmailService.send(
            EmailTemplate.BACKUP_CODE_USED,
            to_email=user.email,
            context={"remaining": remaining_backup_codes(user)},
        )
    return user, kind, data.get("n") or ""


def remember_device(response, user):
    two_factor = settings_for(user)
    if two_factor is None:
        return
    value = signing.dumps(
        {"u": user.pk, "n": two_factor.device_nonce, "p": _password_marker(user)},
        salt=DEVICE_SALT,
    )
    response.set_cookie(
        DEVICE_COOKIE,
        value,
        max_age=DEVICE_MAX_AGE,
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="Lax",
    )


def forget_device(response):
    response.delete_cookie(DEVICE_COOKIE, samesite="Lax")


def remaining_backup_codes(user):
    two_factor = settings_for(user)
    return len(two_factor.backup_codes) if two_factor else 0


# --- turning it on and off ---------------------------------------------------


def start_setup(request, user):
    request.session[SETUP_KEY] = {
        "u": user.pk,
        "s": pyotp.random_base32(),
        "t": int(time.time()),
    }


def pending_setup(request, user):
    data = request.session.get(SETUP_KEY)
    if not data or data["u"] != user.pk or time.time() - data["t"] > SETUP_MAX_AGE:
        request.session.pop(SETUP_KEY, None)
        return None
    return data["s"]


def cancel_setup(request):
    request.session.pop(SETUP_KEY, None)


def setup_details(user, secret):
    """The QR code for the app (inline SVG, no request leaves the site) and
    the same secret in groups of four for typing it in by hand."""
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER)
    svg = segno.make(uri, error="m").svg_inline(
        scale=4, border=2, dark="#18181b", light="#ffffff"
    )
    return {
        "qr_svg": mark_safe(svg),  # noqa: S308 - generated by segno, no user HTML
        "secret_groups": " ".join(secret[i : i + 4] for i in range(0, len(secret), 4)),
    }


def confirm_setup(request, user, code):
    """The first code from the app turns it on. -> backup codes to show."""
    secret = pending_setup(request, user)
    if secret is None:
        raise ValidationAppError(SETUP_EXPIRED_MESSAGE, code="TWO_FACTOR_EXPIRED")
    _check_limits(request, user)
    step = _matching_step(secret, _normalize(code))
    if step is None:
        throttle.record(f"2fa:{user.pk}")
        throttle.record(throttle.ip_key("2fa-ip", request))
        raise ValidationAppError(INVALID_CODE_MESSAGE, code="INVALID_CODE")
    shown, hashed = _new_backup_codes()
    sealed, key_id = encryption.seal(secret.encode(), SECRET_AAD)
    with transaction.atomic():
        TwoFactor.objects.filter(user=user).delete()
        TwoFactor.objects.create(
            user=user,
            secret=sealed,
            secret_key_id=key_id,
            last_step=step,
            backup_codes=hashed,
        )
    cancel_setup(request)
    throttle.clear(f"2fa:{user.pk}")
    AuditService.log(
        AuditEvent.TWO_FACTOR_ENABLED, actor=user, target=user, request=request
    )
    EmailService.send(EmailTemplate.TWO_FACTOR_ENABLED, to_email=user.email)
    return shown


def regenerate_codes(request, user, password, code):
    check_password(request, user, password)
    verify(request, user, code)
    shown, hashed = _new_backup_codes()
    TwoFactor.objects.filter(user=user).update(
        backup_codes=hashed, updated_at=timezone.now()
    )
    AuditService.log(
        AuditEvent.BACKUP_CODES_REGENERATED, actor=user, target=user, request=request
    )
    return shown


def disable(request, user, password, code):
    check_password(request, user, password)
    verify(request, user, code)
    _turn_off(user, request=request, by_team=False)


def admin_disable(user, request=None):
    """For the team, after checking who asks: someone who lost both the
    phone and the backup codes."""
    if is_enabled(user):
        _turn_off(user, request=request, by_team=True)


def _turn_off(user, request, by_team):
    TwoFactor.objects.filter(user=user).delete()
    AuditService.log(
        AuditEvent.TWO_FACTOR_DISABLED,
        actor=request.user if by_team and request else user,
        target=user,
        request=request,
        metadata={"by_team": True} if by_team else None,
    )
    EmailService.send(
        EmailTemplate.TWO_FACTOR_DISABLED,
        to_email=user.email,
        context={"by_team": by_team},
    )


def keep_new_codes(request, codes):
    """Codes are shown once, on the page after the form (so a reload doesn't
    send the form again)."""
    request.session[NEW_CODES_KEY] = codes


def take_new_codes(request):
    return request.session.pop(NEW_CODES_KEY, None)


# --- the panel's hint --------------------------------------------------------


def show_hint(user):
    """A quiet line in the panel for accounts worth protecting: a week old,
    or with files already received. "Nie teraz" hides it for 90 days."""
    from apps.documents.models import Document

    if not can_use(user) or is_enabled(user):
        return False
    hidden_until = user.security_hint_hidden_until
    if hidden_until and hidden_until > timezone.localdate():
        return False
    if user.date_joined <= timezone.now() - HINT_AFTER:
        return True
    return Document.objects.filter(request_item__request__created_by=user).exists()


def hide_hint(user):
    user.security_hint_hidden_until = timezone.localdate() + HINT_SNOOZE
    user.save(update_fields=["security_hint_hidden_until"])
