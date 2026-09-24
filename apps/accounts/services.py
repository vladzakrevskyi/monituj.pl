from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.erasure import erase_account
from apps.accounts.models import AccountToken, AccountTokenPurpose, User
from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.common.exceptions import ValidationAppError
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


class RegistrationService:
    @staticmethod
    def register(email, password, accept_terms, accept_privacy_policy, request=None):
        if User.objects.filter(email__iexact=email).exists():
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
        user = authenticate(request, username=email, password=password)
        if user is None:
            AuditService.log(
                AuditEvent.USER_LOGIN_FAILED, request=request, metadata={"email": email}
            )
            raise ValidationAppError(
                "Nieprawidłowy adres email lub hasło.",
                code="INVALID_CREDENTIALS",
                status_code=401,
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
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            return

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
        user.save(update_fields=["password"])

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
        if not user.check_password(current_password):
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
