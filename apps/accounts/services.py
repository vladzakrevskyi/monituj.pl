from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.erasure import erase_account
from apps.accounts.models import AccountToken, AccountTokenPurpose, GuestAccess, User
from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.common import throttle
from apps.common.exceptions import RateLimitedAppError, ValidationAppError
from apps.common.security import generate_public_token, hash_token
from apps.common.site import absolute_url
from apps.documents.models import Document
from apps.notifications.models import EmailTemplate
from apps.notifications.services import NOT_DELIVERED, EmailService
from apps.requests.models import Request

EMAIL_VERIFICATION_TTL = timedelta(hours=48)
PASSWORD_RESET_TTL = timedelta(hours=2)
PASSWORD_CHANGE_TTL = timedelta(hours=1)
EMAIL_CHANGE_TTL = timedelta(hours=1)
ACCOUNT_DELETION_TTL = timedelta(hours=1)

GUEST_OWNER_EMAIL = "goscie@monituj.pl"


def _validate_password_strength(raw_password, user=None):
    try:
        validate_password(raw_password, user=user)
    except DjangoValidationError as exc:
        raise ValidationAppError(" ".join(exc.messages), code="WEAK_PASSWORD") from exc


class GuestOwnerService:
    """Requests and clients created through a public, no-account flow still
    need an owner to satisfy Request/Client's NOT NULL owner FK. This single
    reserved, unloggable-into account holds all of them so ownership-scoped
    queries elsewhere keep working unchanged; nobody is ever given its
    credentials."""

    @staticmethod
    def get_or_create():
        user, created = User.objects.get_or_create(
            email=GUEST_OWNER_EMAIL, defaults={"is_active": False}
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user


def _is_unclaimed(user):
    return (
        user.email_verified_at is None
        and user.is_active
        and not hasattr(user, "guest_access")
        and not hasattr(user, "demo_account")
        and not user.requests.exists()
        and not user.clients.exists()
    )


REGISTRATIONS_PER_IP_HOUR = 5
RESETS_PER_EMAIL_HOUR = 3
RESETS_PER_IP_HOUR = 10
LOGIN_FAILURES_PER_IP = 20
LOGIN_FAILURES_PER_EMAIL = 8
LOGIN_WINDOW = timedelta(minutes=15)


class RegistrationService:
    @staticmethod
    def register(email, password, accept_terms, accept_privacy_policy, request=None):
        if request is not None:
            throttle.consume(
                throttle.ip_key("register", request),
                REGISTRATIONS_PER_IP_HOUR,
                throttle.HOUR,
                "Z tego adresu założono już kilka kont. Spróbuj ponownie za godzinę.",
                code="REGISTER_LIMIT_REACHED",
            )
        existing = User.objects.filter(email__iexact=email).first()
        if existing is not None and hasattr(existing, "guest_access"):
            raise ValidationAppError(
                "Z tego adresu wysłano już prośbę bez konta, więc masz konto bez "
                "hasła. Ustaw hasło przez „Nie pamiętasz hasła?” na stronie "
                "logowania.",
                code="EMAIL_TAKEN",
            )
        # An account nobody ever confirmed proves nothing about who owns the
        # address - e.g. someone registered it to block the real owner. It
        # can't be used and holds no data, so registering again takes it over.
        unclaimed = existing is not None and _is_unclaimed(existing)
        if existing is not None and not unclaimed:
            raise ValidationAppError(
                "Konto z tym adresem email już istnieje.", code="EMAIL_TAKEN"
            )
        if not accept_terms or not accept_privacy_policy:
            raise ValidationAppError(
                "Musisz zaakceptować regulamin i politykę prywatności.",
                code="CONSENT_REQUIRED",
            )
        _validate_password_strength(password)

        now = timezone.now()
        if unclaimed:
            user = existing
            user.set_password(password)
            user.terms_accepted_at = now
            user.privacy_policy_accepted_at = now
            user.save(
                update_fields=[
                    "password",
                    "terms_accepted_at",
                    "privacy_policy_accepted_at",
                ]
            )
        else:
            user = User.objects.create_user(
                email=email,
                password=password,
                terms_accepted_at=now,
                privacy_policy_accepted_at=now,
            )
        AuditService.log(
            AuditEvent.USER_REGISTERED, actor=user, target=user, request=request
        )
        VerificationService.send_verification_email(user)
        return user


class VerificationService:
    @staticmethod
    def send_verification_email(user):
        raw_token = generate_public_token()
        AccountToken.objects.create(
            user=user,
            purpose=AccountTokenPurpose.EMAIL_VERIFICATION,
            token_hash=hash_token(raw_token),
            expires_at=timezone.now() + EMAIL_VERIFICATION_TTL,
        )
        verification_url = absolute_url(f"/weryfikacja-email/{raw_token}/")
        EmailService.send(
            EmailTemplate.EMAIL_VERIFICATION,
            to_email=user.email,
            context={"verification_url": verification_url},
        )

    @staticmethod
    def verify(raw_token, request=None):
        token_hash = hash_token(raw_token)
        token = (
            AccountToken.objects.select_related("user")
            .filter(
                token_hash=token_hash, purpose=AccountTokenPurpose.EMAIL_VERIFICATION
            )
            .first()
        )
        if token is None or not token.is_valid:
            raise ValidationAppError(
                "Link jest nieprawidłowy lub wygasł.", code="INVALID_TOKEN"
            )

        token.used_at = timezone.now()
        token.save(update_fields=["used_at"])

        user = token.user
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])

        AuditService.log(
            AuditEvent.EMAIL_VERIFIED, actor=user, target=user, request=request
        )
        return user


class AuthenticationService:
    @staticmethod
    def login(request, email, password):
        ip_key = throttle.ip_key("login-ip", request)
        email_key = "login-email:" + hash_token(email.strip().lower())
        if throttle.is_limited(
            ip_key, LOGIN_FAILURES_PER_IP, LOGIN_WINDOW
        ) or throttle.is_limited(email_key, LOGIN_FAILURES_PER_EMAIL, LOGIN_WINDOW):
            raise RateLimitedAppError(
                "Zbyt wiele nieudanych prób logowania. Spróbuj ponownie za 15 minut "
                "albo zresetuj hasło.",
                code="LOGIN_LIMIT_REACHED",
            )

        user = authenticate(request, username=email, password=password)
        if user is None:
            throttle.record(ip_key)
            throttle.record(email_key)
            AuditService.log(
                AuditEvent.USER_LOGIN_FAILED, request=request, metadata={"email": email}
            )
            raise ValidationAppError(
                "Nieprawidłowy adres email lub hasło.",
                code="INVALID_CREDENTIALS",
                status_code=401,
            )
        throttle.clear(email_key)
        if user.email_verified_at is None:
            # The password is right, so help rather than just refuse: send the
            # confirmation link again (not more often than every few minutes).
            resend_key = f"verify-resend:{user.pk}"
            if not throttle.is_limited(resend_key, 1, timedelta(minutes=5)):
                throttle.record(resend_key)
                VerificationService.send_verification_email(user)
            raise ValidationAppError(
                f"Najpierw potwierdź adres email – link wysłaliśmy na {user.email}. "
                "Po kliknięciu zalogujesz się automatycznie.",
                code="EMAIL_NOT_VERIFIED",
            )
        django_login(request, user)
        AuditService.log(
            AuditEvent.USER_LOGIN, actor=user, target=user, request=request
        )
        return user

    @staticmethod
    def logout(request):
        user = request.user if request.user.is_authenticated else None
        django_logout(request)
        AuditService.log(AuditEvent.USER_LOGOUT, actor=user, request=request)


class PasswordResetService:
    @staticmethod
    def request_reset(email, request=None):
        if request is not None:
            throttle.consume(
                throttle.ip_key("reset-ip", request),
                RESETS_PER_IP_HOUR,
                throttle.HOUR,
                "Zbyt wiele próśb o reset hasła. Spróbuj ponownie za godzinę.",
                code="RESET_LIMIT_REACHED",
            )
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            return
        # Silently: the reply must not reveal whether the account exists.
        email_key = f"reset-email:{user.pk}"
        if throttle.is_limited(email_key, RESETS_PER_EMAIL_HOUR, throttle.HOUR):
            return
        throttle.record(email_key)

        raw_token = generate_public_token()
        AccountToken.objects.create(
            user=user,
            purpose=AccountTokenPurpose.PASSWORD_RESET,
            token_hash=hash_token(raw_token),
            expires_at=timezone.now() + PASSWORD_RESET_TTL,
        )
        reset_url = absolute_url(f"/reset-hasla/{raw_token}/")
        EmailService.send(
            EmailTemplate.PASSWORD_RESET,
            to_email=user.email,
            context={"reset_url": reset_url},
        )

    @staticmethod
    def confirm_reset(raw_token, new_password, request=None):
        token_hash = hash_token(raw_token)
        token = (
            AccountToken.objects.select_related("user")
            .filter(token_hash=token_hash, purpose=AccountTokenPurpose.PASSWORD_RESET)
            .first()
        )
        if token is None or not token.is_valid:
            raise ValidationAppError(
                "Link jest nieprawidłowy lub wygasł.", code="INVALID_TOKEN"
            )

        user = token.user
        _validate_password_strength(new_password, user=user)
        user.set_password(new_password)
        # The reset link came to this address, which proves who owns it.
        user.email_verified_at = user.email_verified_at or timezone.now()
        user.save(update_fields=["password", "email_verified_at"])
        # A passwordless account becomes a regular one: the permanent panel
        # link stops working and the daily limit is gone.
        GuestAccess.objects.filter(user=user).delete()

        token.used_at = timezone.now()
        token.save(update_fields=["used_at"])
        AccountToken.objects.filter(
            user=user, purpose=AccountTokenPurpose.PASSWORD_RESET, used_at__isnull=True
        ).exclude(pk=token.pk).update(used_at=timezone.now())

        AuditService.log(
            AuditEvent.PASSWORD_CHANGED, actor=user, target=user, request=request
        )
        return user


class ProfileService:
    @staticmethod
    def update_profile(user, display_name, request=None):
        user.display_name = display_name.strip()
        user.save(update_fields=["display_name"])
        AuditService.log(
            AuditEvent.PROFILE_UPDATED, actor=user, target=user, request=request
        )
        return user


class PasswordChangeService:
    """Changing password while logged in: the current password proves it's
    really the owner, but the change itself only takes effect once the
    confirmation link mailed to the account's own address is clicked - and
    since that click never refreshes the requesting session's auth hash,
    every session (this one included) is signed out by Django's normal
    session-auth-hash check, satisfying the "log out everywhere" requirement
    without needing to enumerate sessions."""

    @staticmethod
    def request_change(user, current_password, new_password, request=None):
        if not user.check_password(current_password):
            raise ValidationAppError(
                "Nieprawidłowe obecne hasło.", code="INVALID_CURRENT_PASSWORD"
            )
        _validate_password_strength(new_password, user=user)

        raw_token = generate_public_token()
        AccountToken.objects.create(
            user=user,
            purpose=AccountTokenPurpose.PASSWORD_CHANGE,
            token_hash=hash_token(raw_token),
            expires_at=timezone.now() + PASSWORD_CHANGE_TTL,
            metadata=make_password(new_password),
        )
        confirm_url = absolute_url(f"/ustawienia/haslo/potwierdz/{raw_token}/")
        EmailService.send(
            EmailTemplate.PASSWORD_CHANGE_CONFIRM,
            to_email=user.email,
            context={"confirm_url": confirm_url},
        )
        AuditService.log(
            AuditEvent.PASSWORD_CHANGE_REQUESTED,
            actor=user,
            target=user,
            request=request,
        )

    @staticmethod
    def confirm_change(raw_token, request=None):
        token_hash = hash_token(raw_token)
        token = (
            AccountToken.objects.select_related("user")
            .filter(token_hash=token_hash, purpose=AccountTokenPurpose.PASSWORD_CHANGE)
            .first()
        )
        if token is None or not token.is_valid:
            raise ValidationAppError(
                "Link jest nieprawidłowy lub wygasł.", code="INVALID_TOKEN"
            )

        user = token.user
        user.password = token.metadata
        user.save(update_fields=["password"])
        # An account without a password becomes a regular one.
        GuestAccess.objects.filter(user=user).delete()

        token.used_at = timezone.now()
        token.save(update_fields=["used_at"])
        AccountToken.objects.filter(
            user=user,
            purpose=AccountTokenPurpose.PASSWORD_CHANGE,
            used_at__isnull=True,
        ).exclude(pk=token.pk).update(used_at=timezone.now())

        AuditService.log(
            AuditEvent.PASSWORD_CHANGED, actor=user, target=user, request=request
        )
        EmailService.send(EmailTemplate.PASSWORD_CHANGED_NOTICE, to_email=user.email)
        return user


class EmailChangeService:
    """Changing the login email is gated on proving ownership of the new
    address (a confirmation link sent there - a correct current password
    alone isn't proof of that), with the old address notified both when the
    change is requested and once it's actually applied, so a hijacked
    session can't silently take over the account's contact address."""

    @staticmethod
    def request_change(user, new_email, current_password, request=None):
        if not user.check_password(current_password):
            raise ValidationAppError(
                "Nieprawidłowe obecne hasło.", code="INVALID_CURRENT_PASSWORD"
            )
        normalized_email = User.objects.normalize_email(new_email.strip())
        if normalized_email.lower() == user.email.lower():
            raise ValidationAppError(
                "To jest już Twój obecny adres email.", code="EMAIL_UNCHANGED"
            )
        if User.objects.filter(email__iexact=normalized_email).exists():
            raise ValidationAppError(
                "Ten adres email jest już zajęty.", code="EMAIL_TAKEN"
            )

        raw_token = generate_public_token()
        AccountToken.objects.create(
            user=user,
            purpose=AccountTokenPurpose.EMAIL_CHANGE,
            token_hash=hash_token(raw_token),
            expires_at=timezone.now() + EMAIL_CHANGE_TTL,
            metadata=normalized_email,
        )
        confirm_url = absolute_url(f"/ustawienia/email/potwierdz/{raw_token}/")
        EmailService.send(
            EmailTemplate.EMAIL_CHANGE_CONFIRM,
            to_email=normalized_email,
            context={"confirm_url": confirm_url},
        )
        EmailService.send(
            EmailTemplate.EMAIL_CHANGE_REQUESTED_NOTICE,
            to_email=user.email,
            context={"new_email": normalized_email},
        )
        AuditService.log(
            AuditEvent.EMAIL_CHANGE_REQUESTED,
            actor=user,
            target=user,
            request=request,
            metadata={"new_email": normalized_email},
        )

    @staticmethod
    def confirm_change(raw_token, request=None):
        token_hash = hash_token(raw_token)
        token = (
            AccountToken.objects.select_related("user")
            .filter(token_hash=token_hash, purpose=AccountTokenPurpose.EMAIL_CHANGE)
            .first()
        )
        if token is None or not token.is_valid:
            raise ValidationAppError(
                "Link jest nieprawidłowy lub wygasł.", code="INVALID_TOKEN"
            )

        new_email = token.metadata
        user = token.user
        if User.objects.filter(email__iexact=new_email).exclude(pk=user.pk).exists():
            raise ValidationAppError(
                "Ten adres email został już zajęty. Spróbuj ponownie z innym adresem.",
                code="EMAIL_TAKEN",
            )

        old_email = user.email
        user.email = new_email
        user.save(update_fields=["email"])

        token.used_at = timezone.now()
        token.save(update_fields=["used_at"])
        AccountToken.objects.filter(
            user=user, purpose=AccountTokenPurpose.EMAIL_CHANGE, used_at__isnull=True
        ).exclude(pk=token.pk).update(used_at=timezone.now())

        AuditService.log(
            AuditEvent.EMAIL_CHANGED,
            actor=user,
            target=user,
            request=request,
            metadata={"old_email": old_email, "new_email": new_email},
        )
        EmailService.send(
            EmailTemplate.EMAIL_CHANGED_NOTICE,
            to_email=old_email,
            context={"new_email": new_email},
        )
        return user


class AccountDeletionService:
    """Deleting an account takes two proofs: the current password, then a
    click on a link mailed to the account's address (and an explicit button
    on the page it opens, so mail scanners prefetching the link can't trigger
    it). Deletion is then immediate and complete - Monituj only processes
    the documents on the user's behalf, so it keeps nothing once the account
    is gone. Recipients of still-relevant requests are told the link is dead
    and their files are removed."""

    @staticmethod
    def request_deletion(user, current_password, request=None):
        # Accounts without a password prove themselves by the email link alone.
        if user.has_usable_password() and not user.check_password(current_password):
            raise ValidationAppError(
                "Nieprawidłowe obecne hasło.", code="INVALID_CURRENT_PASSWORD"
            )

        raw_token = generate_public_token()
        AccountToken.objects.create(
            user=user,
            purpose=AccountTokenPurpose.ACCOUNT_DELETION,
            token_hash=hash_token(raw_token),
            expires_at=timezone.now() + ACCOUNT_DELETION_TTL,
        )
        confirm_url = absolute_url(
            reverse("accounts:account-deletion-confirm", args=[raw_token])
        )
        EmailService.send(
            EmailTemplate.ACCOUNT_DELETION_CONFIRM,
            to_email=user.email,
            context={
                "confirm_url": confirm_url,
                **AccountDeletionService.summary(user),
            },
        )
        AuditService.log(
            AuditEvent.ACCOUNT_DELETION_REQUESTED,
            actor=user,
            target=user,
            request=request,
        )

    @staticmethod
    def pending_token(raw_token):
        token = (
            AccountToken.objects.select_related("user")
            .filter(
                token_hash=hash_token(raw_token),
                purpose=AccountTokenPurpose.ACCOUNT_DELETION,
            )
            .first()
        )
        if token is None or not token.is_valid:
            raise ValidationAppError(
                "Link jest nieprawidłowy lub wygasł.", code="INVALID_TOKEN"
            )
        return token

    @staticmethod
    def summary(user):
        requests = Request.objects.filter(created_by=user)
        return {
            "clients_count": user.clients.count(),
            "requests_count": requests.count(),
            "files_count": Document.objects.filter(
                request_item__request__in=requests, anonymized_at__isnull=True
            ).count(),
        }

    @staticmethod
    def _recipient_notices(user):
        """One notice per request whose recipient could still act on it: it
        is waiting for documents, or it holds files they sent."""
        notices = []
        requests = Request.objects.filter(created_by=user).select_related("client")
        for request_obj in requests:
            waiting = request_obj.items.filter(status__in=NOT_DELIVERED).exists()
            files = Document.objects.filter(
                request_item__request=request_obj, anonymized_at__isnull=True
            ).exists()
            if waiting or files:
                notices.append(
                    {
                        "to_email": request_obj.client.email,
                        "request_name": request_obj.name,
                        "had_files": files,
                    }
                )
        return notices

    @staticmethod
    def confirm(raw_token, request=None):
        token = AccountDeletionService.pending_token(raw_token)
        user = token.user
        email = user.email
        sender_name = user.display_name
        notices = AccountDeletionService._recipient_notices(user)

        if (
            request is not None
            and request.user.is_authenticated
            and request.user.pk == user.pk
        ):
            django_logout(request)
        erase_account(user)

        # Sent without logging: the log rows would themselves be data about
        # the erased account and its recipients.
        for notice in notices:
            EmailService.send(
                EmailTemplate.REQUEST_CANCELLED,
                to_email=notice.pop("to_email"),
                context={"sender_name": sender_name, **notice},
                log=False,
            )
        EmailService.send(
            EmailTemplate.ACCOUNT_DELETED,
            to_email=email,
            context={"backup_days": settings.LEGAL_ENTITY.get("backup_days", "")},
            log=False,
        )
        return email


GUEST_EMAIL_LINK_MAX_AGE = timedelta(days=14)
GUEST_EMAIL_LINK_SALT = "guest-email-link"
ACCESS_LINKS_PER_EMAIL_HOUR = 3
ACCESS_LINKS_PER_IP_HOUR = 10
INVALID_ACCESS_MESSAGE = "Ten link nie działa. Jeśli masz już hasło, zaloguj się nim."


class GuestAccessService:
    """Accounts without a password. Their one permanent link arrives only in
    the "Twój panel" email; everyday emails carry a link that works for 14
    days, so an old forwarded email doesn't open the panel for good."""

    @staticmethod
    def user_for(token):
        access = (
            GuestAccess.objects.select_related("user")
            .filter(token=token, user__is_active=True)
            .first()
        )
        if access is None or access.user.email_verified_at is None:
            raise ValidationAppError(INVALID_ACCESS_MESSAGE, code="INVALID_TOKEN")
        return access.user

    @staticmethod
    def email_link_token(user):
        return signing.dumps(
            {"u": user.pk, "t": user.guest_access.token[:16]},
            salt=GUEST_EMAIL_LINK_SALT,
            compress=True,
        )

    @staticmethod
    def user_for_email_link(signed):
        """The account behind a 14-day link. An expired one raises with the
        account attached, so the page can offer to send a fresh link."""
        try:
            data = signing.loads(
                signed,
                salt=GUEST_EMAIL_LINK_SALT,
                max_age=GUEST_EMAIL_LINK_MAX_AGE,
            )
            expired = False
        except signing.SignatureExpired:
            data = signing.loads(signed, salt=GUEST_EMAIL_LINK_SALT)
            expired = True
        except signing.BadSignature as exc:
            raise ValidationAppError(
                INVALID_ACCESS_MESSAGE, code="INVALID_TOKEN"
            ) from exc
        user = (
            User.objects.filter(pk=data.get("u"), is_active=True)
            .select_related("guest_access")
            .first()
        )
        # A newer link (or a password) replaces every older one.
        if (
            user is None
            or not hasattr(user, "guest_access")
            or not user.guest_access.token.startswith(data.get("t", "-"))
            or user.email_verified_at is None
        ):
            raise ValidationAppError(INVALID_ACCESS_MESSAGE, code="INVALID_TOKEN")
        if expired:
            error = ValidationAppError(
                "Ten link wygasł – linki z wiadomości działają przez 14 dni.",
                code="LINK_EXPIRED",
            )
            error.user = user
            raise error
        return user

    @staticmethod
    def login(request, user):
        django_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        AuditService.log(
            AuditEvent.USER_LOGIN, actor=user, target=user, request=request
        )

    @staticmethod
    def send_access_link(email, request=None):
        """Mails the permanent panel link again (lost or expired links).
        Answers the same way whether or not such an account exists."""
        if request is not None:
            throttle.consume(
                throttle.ip_key("access-link", request),
                ACCESS_LINKS_PER_IP_HOUR,
                throttle.HOUR,
            )
        user = User.objects.filter(
            email__iexact=email, is_active=True, email_verified_at__isnull=False
        ).first()
        if user is None or not hasattr(user, "guest_access"):
            return
        key = f"access-link:{user.pk}"
        if throttle.is_limited(key, ACCESS_LINKS_PER_EMAIL_HOUR, throttle.HOUR):
            return
        throttle.record(key)
        GuestAccessService._mail_access_link(user)

    @staticmethod
    def rotate(user, request=None):
        """A new permanent link; every older link (permanent or from emails)
        stops working. For when a link may have reached someone else."""
        user.guest_access.token = generate_public_token()
        user.guest_access.save(update_fields=["token"])
        GuestAccessService._mail_access_link(user)

    @staticmethod
    def _mail_access_link(user):
        from apps.requests.links import guest_panel_url

        EmailService.send(
            EmailTemplate.GUEST_PANEL_ACCESS,
            to_email=user.email,
            context={"access_url": guest_panel_url(user)},
        )

    @staticmethod
    def request_password(user, new_password, request=None):
        """Setting a password needs a click in the account's inbox: whoever
        only got hold of a panel link can't lock the owner out."""
        _validate_password_strength(new_password, user=user)
        raw_token = generate_public_token()
        AccountToken.objects.create(
            user=user,
            purpose=AccountTokenPurpose.PASSWORD_CHANGE,
            token_hash=hash_token(raw_token),
            expires_at=timezone.now() + PASSWORD_CHANGE_TTL,
            metadata=make_password(new_password),
        )
        EmailService.send(
            EmailTemplate.PASSWORD_CHANGE_CONFIRM,
            to_email=user.email,
            context={
                "confirm_url": absolute_url(f"/ustawienia/haslo/potwierdz/{raw_token}/")
            },
        )
        AuditService.log(
            AuditEvent.PASSWORD_CHANGE_REQUESTED,
            actor=user,
            target=user,
            request=request,
        )
