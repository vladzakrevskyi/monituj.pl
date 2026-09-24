"""Sign in with Google: what a verified Google identity may do here.

The rules, so that Google and email + password never get in each other's way
and never open an account for the wrong person:

1. An account is found by Google's permanent id (`sub`), not by address.
2. First Google sign-in with an address Monituj already knows:
   - Gmail / Google Workspace address (Google runs the mailbox): linked at
     once - whoever holds that mailbox could reset the password anyway;
   - any other address: linked only after a click in a confirmation email,
     opened in the same browser. Google checked such an address once, long
     ago; the mailbox may have changed hands since.
3. New address: an account is created after accepting the terms - at once
   for Gmail / Workspace, after the same email confirmation otherwise.
4. An account someone registered but never confirmed belongs to whoever
   proves the mailbox: linking removes the password set by that someone.
5. Every new link is announced by email to the account's address.
6. Google can be disconnected only while a password exists - no lockouts.
"""

import hmac
import secrets
import time
from enum import Enum

from django.contrib.auth import login as django_login
from django.core import signing
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.accounts.google import GoogleIdentity
from apps.accounts.models import GoogleAccount, GuestAccess, User
from apps.accounts.services import REGISTRATIONS_PER_IP_HOUR
from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.common import throttle
from apps.common.exceptions import ValidationAppError
from apps.common.site import absolute_url
from apps.consents.models import AcceptanceMethod
from apps.consents.services import record_acceptance
from apps.demo.models import is_demo_user
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService

SIGNUP_SESSION_KEY = "google_signup"
CONFIRM_SESSION_KEY = "google_confirm"
SIGNUP_MAX_AGE = 15 * 60
CONFIRM_SALT = "google-confirm"
CONFIRM_MAX_AGE = 30 * 60
CONFIRMS_PER_ACCOUNT_HOUR = 3
SIGN_INS_PER_IP_HOUR = 30
BACKEND = "django.contrib.auth.backends.ModelBackend"

UNAVAILABLE_MESSAGE = "Na to konto nie można zalogować się przez Google."
OTHER_GOOGLE_MESSAGE = (
    "To konto Monituj jest już połączone z innym kontem Google. Zaloguj się "
    "tamtym kontem Google albo adresem email i hasłem."
)
GOOGLE_TAKEN_MESSAGE = "To konto Google jest już połączone z innym kontem Monituj."
SIGNUP_EXPIRED_MESSAGE = (
    "Zakładanie konta trwało zbyt długo. Zacznij ponownie od przycisku Google."
)
CONFIRM_INVALID_MESSAGE = (
    "Link jest nieprawidłowy albo wygasł. Zaloguj się przez Google jeszcze raz."
)
CONFIRM_OTHER_BROWSER_MESSAGE = (
    "Otwórz link w tej samej przeglądarce, w której klikałeś „Zaloguj się przez "
    "Google” – albo zacznij tutaj od nowa."
)


class Outcome(Enum):
    LOGGED_IN = "logged_in"
    SIGNUP = "signup"  # show the terms, then create the account
    CONFIRM_SENT = "confirm_sent"  # waiting for the click in the email


def consume_attempt(request):
    throttle.consume(
        throttle.ip_key("google", request),
        SIGN_INS_PER_IP_HOUR,
        throttle.HOUR,
        "Zbyt wiele prób logowania przez Google. Spróbuj ponownie za godzinę.",
        code="GOOGLE_LIMIT_REACHED",
    )


def _check_allowed(user):
    # Inactive covers the shared no-account owner; demo accounts have fake
    # addresses and must never be reachable from outside.
    if not user.is_active or is_demo_user(user):
        raise ValidationAppError(UNAVAILABLE_MESSAGE, code="GOOGLE_UNAVAILABLE")


def _login(request, user, account):
    account.email = account.email or user.email
    account.last_login_at = timezone.now()
    account.save(update_fields=["email", "last_login_at", "updated_at"])
    django_login(request, user, backend=BACKEND)
    AuditService.log(
        AuditEvent.USER_LOGIN,
        actor=user,
        target=user,
        request=request,
        metadata={"method": "google"},
    )


def _link(user, identity, request):
    """Adds Google to the account. The caller has made sure the person
    controls the account's mailbox (or is signed in to the account)."""
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        if user.email_verified_at is None:
            # Registered by someone who never proved the address; the mailbox
            # owner has now. A password that someone chose must not stay.
            user.set_unusable_password()
            user.email_verified_at = timezone.now()
            user.save(update_fields=["password", "email_verified_at"])
        # Google is a real sign-in: a passwordless account stops depending
        # on links from emails (and loses the one-request-a-day limit).
        GuestAccess.objects.filter(user=user).delete()
        try:
            with transaction.atomic():
                account = GoogleAccount.objects.create(
                    user=user, subject=identity.subject, email=identity.email
                )
        except IntegrityError as exc:
            raise ValidationAppError(GOOGLE_TAKEN_MESSAGE, code="GOOGLE_TAKEN") from exc
    AuditService.log(
        AuditEvent.GOOGLE_LINKED,
        actor=user,
        target=user,
        request=request,
        metadata={"google_email": identity.email},
    )
    EmailService.send(
        EmailTemplate.GOOGLE_LINKED,
        to_email=user.email,
        context={"google_email": identity.email},
    )
    return user, account


def _send_confirmation(request, identity, user=None, consents=False):
    """One email to the address; the click must come from this browser."""
    email = user.email if user is not None else identity.email
    key = "google-confirm:" + (str(user.pk) if user else email.lower())
    if throttle.is_limited(key, CONFIRMS_PER_ACCOUNT_HOUR, throttle.HOUR):
        return email  # quietly: the earlier email is still on its way
    throttle.record(key)
    browser_nonce = secrets.token_urlsafe(24)
    request.session[CONFIRM_SESSION_KEY] = browser_nonce
    signed = signing.dumps(
        {
            "s": identity.subject,
            "g": identity.email,
            "u": user.pk if user else None,
            "m": email.lower(),
            "c": bool(consents),
            "n": browser_nonce,
        },
        salt=CONFIRM_SALT,
        compress=True,
    )
    EmailService.send(
        EmailTemplate.GOOGLE_LINK_CONFIRM,
        to_email=email,
        context={
            "confirm_url": absolute_url(
                reverse("accounts:google-confirm", args=[signed])
            ),
            "google_email": identity.email,
            "new_account": user is None,
        },
    )
    return email


class GoogleAuthService:
    @staticmethod
    def sign_in(request, identity):
        account = (
            GoogleAccount.objects.select_related("user")
            .filter(subject=identity.subject)
            .first()
        )
        if account is not None:
            _check_allowed(account.user)
            account.email = identity.email
            _login(request, account.user, account)
            return Outcome.LOGGED_IN, account.user

        user = User.objects.filter(email__iexact=identity.email).first()
        if user is None:
            request.session[SIGNUP_SESSION_KEY] = {
                "s": identity.subject,
                "g": identity.email,
                "a": identity.authoritative,
                "t": int(time.time()),
            }
            return Outcome.SIGNUP, None

        _check_allowed(user)
        if hasattr(user, "google_account"):
            raise ValidationAppError(OTHER_GOOGLE_MESSAGE, code="GOOGLE_OTHER")
        if identity.authoritative:
            user, account = _link(user, identity, request)
            _login(request, user, account)
            return Outcome.LOGGED_IN, user
        return Outcome.CONFIRM_SENT, _send_confirmation(request, identity, user=user)

    @staticmethod
    def pending_signup(request):
        data = request.session.get(SIGNUP_SESSION_KEY)
        if not data or time.time() - data["t"] > SIGNUP_MAX_AGE:
            request.session.pop(SIGNUP_SESSION_KEY, None)
            raise ValidationAppError(SIGNUP_EXPIRED_MESSAGE, code="GOOGLE_SIGNUP")
        return GoogleIdentity(
            subject=data["s"], email=data["g"], authoritative=data["a"]
        )

    @staticmethod
    def complete_signup(request, accept_terms, accept_privacy_policy):
        identity = GoogleAuthService.pending_signup(request)
        if not accept_terms or not accept_privacy_policy:
            raise ValidationAppError(
                "Musisz zaakceptować regulamin i politykę prywatności.",
                code="CONSENT_REQUIRED",
            )
        throttle.consume(
            throttle.ip_key("register", request),
            REGISTRATIONS_PER_IP_HOUR,
            throttle.HOUR,
            "Z tego adresu założono już kilka kont. Spróbuj ponownie za godzinę.",
            code="REGISTER_LIMIT_REACHED",
        )
        request.session.pop(SIGNUP_SESSION_KEY, None)
        if not identity.authoritative:
            return Outcome.CONFIRM_SENT, _send_confirmation(
                request, identity, consents=True
            )
        user, account = GoogleAuthService._create_account(identity, request)
        _login(request, user, account)
        return Outcome.LOGGED_IN, user

    @staticmethod
    def _create_account(identity, request):
        if (
            User.objects.filter(email__iexact=identity.email).exists()
            or GoogleAccount.objects.filter(subject=identity.subject).exists()
        ):
            # Created meanwhile (another tab, the password form): sign in anew.
            raise ValidationAppError(
                "Konto z tym adresem już istnieje. Zaloguj się przez Google "
                "jeszcze raz.",
                code="EMAIL_TAKEN",
            )
        now = timezone.now()
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=identity.email,
                    password=None,  # unusable - Google is the way in
                    email_verified_at=now,
                    terms_accepted_at=now,
                    privacy_policy_accepted_at=now,
                )
                account = GoogleAccount.objects.create(
                    user=user, subject=identity.subject, email=identity.email
                )
        except IntegrityError as exc:
            raise ValidationAppError(
                "Konto z tym adresem już istnieje. Zaloguj się przez Google "
                "jeszcze raz.",
                code="EMAIL_TAKEN",
            ) from exc
        AuditService.log(
            AuditEvent.USER_REGISTERED,
            actor=user,
            target=user,
            request=request,
            metadata={"method": "google"},
        )
        record_acceptance(user, AcceptanceMethod.GOOGLE, request)
        return user, account

    @staticmethod
    def pending_confirmation(signed):
        try:
            data = signing.loads(signed, salt=CONFIRM_SALT, max_age=CONFIRM_MAX_AGE)
        except signing.BadSignature as exc:
            raise ValidationAppError(
                CONFIRM_INVALID_MESSAGE, code="INVALID_TOKEN"
            ) from exc
        return data

    @staticmethod
    def confirm(request, signed):
        data = GoogleAuthService.pending_confirmation(signed)
        expected = request.session.get(CONFIRM_SESSION_KEY) or ""
        if not hmac.compare_digest(str(data.get("n", "")), expected):
            raise ValidationAppError(
                CONFIRM_OTHER_BROWSER_MESSAGE, code="GOOGLE_OTHER_BROWSER"
            )
        identity = GoogleIdentity(
            subject=data["s"], email=data["g"], authoritative=False
        )
        if data["u"] is None:
            if not data.get("c"):
                raise ValidationAppError(CONFIRM_INVALID_MESSAGE, code="INVALID_TOKEN")
            user, account = GoogleAuthService._create_account(identity, request)
        else:
            user = User.objects.filter(pk=data["u"]).first()
            # The address the email went to must still be the account's.
            if user is None or user.email.lower() != data["m"]:
                raise ValidationAppError(CONFIRM_INVALID_MESSAGE, code="INVALID_TOKEN")
            _check_allowed(user)
            existing = getattr(user, "google_account", None)
            if existing is not None and existing.subject != identity.subject:
                raise ValidationAppError(OTHER_GOOGLE_MESSAGE, code="GOOGLE_OTHER")
            if existing is None:
                user, account = _link(user, identity, request)
            else:
                account = existing
        request.session.pop(CONFIRM_SESSION_KEY, None)
        _login(request, user, account)
        return user

    @staticmethod
    def connect(user, identity, request):
        """Adds Google to the signed-in account - any Google address will do,
        the person has just proved both sides."""
        _check_allowed(user)
        if hasattr(user, "google_account"):
            raise ValidationAppError(
                "Twoje konto jest już połączone z Google.", code="GOOGLE_ALREADY"
            )
        if GoogleAccount.objects.filter(subject=identity.subject).exists():
            raise ValidationAppError(GOOGLE_TAKEN_MESSAGE, code="GOOGLE_TAKEN")
        return _link(user, identity, request)

    @staticmethod
    def disconnect(user, request):
        account = getattr(user, "google_account", None)
        if account is None:
            raise ValidationAppError(
                "Twoje konto nie jest połączone z Google.", code="GOOGLE_NOT_LINKED"
            )
        if not user.has_usable_password():
            raise ValidationAppError(
                "Najpierw ustaw hasło – bez niego nie mógłbyś się zalogować.",
                code="PASSWORD_REQUIRED",
            )
        google_email = account.email
        account.delete()
        AuditService.log(
            AuditEvent.GOOGLE_UNLINKED,
            actor=user,
            target=user,
            request=request,
            metadata={"google_email": google_email},
        )
        EmailService.send(
            EmailTemplate.GOOGLE_UNLINKED,
            to_email=user.email,
            context={"google_email": google_email},
        )
