from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel
from apps.common.security import generate_public_token


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None  # type: ignore[assignment]
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=255, blank=True)
    # Recipients see the name and NIP of the firm paying for the account only
    # with the owner's consent (Ustawienia); without it - that the account is
    # a paid business one, nothing more.
    show_paying_firm = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    privacy_policy_accepted_at = models.DateTimeField(null=True, blank=True)
    # IANA zone reported by the browser (apps.common.timezones).
    timezone = models.CharField(max_length=64, default="Europe/Warsaw")
    # "Nie teraz" on the panel's two-step verification hint hides it until
    # this day.
    security_hint_hidden_until = models.DateField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []  # type: ignore[misc]

    objects = UserManager()  # type: ignore[misc,assignment]

    def __str__(self):
        return self.email

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None


class AccountTokenPurpose(models.TextChoices):
    EMAIL_VERIFICATION = "email_verification", "Weryfikacja email"
    PASSWORD_RESET = "password_reset", "Reset hasła"
    PASSWORD_CHANGE = "password_change", "Zmiana hasła"
    EMAIL_CHANGE = "email_change", "Zmiana email"
    ACCOUNT_DELETION = "account_deletion", "Usunięcie konta"


class AccountToken(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tokens")
    purpose = models.CharField(max_length=32, choices=AccountTokenPurpose.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    # Holds the pending value a token confirms: the new (already-hashed)
    # password for PASSWORD_CHANGE, or the pending new email address for
    # EMAIL_CHANGE. Unused by EMAIL_VERIFICATION/PASSWORD_RESET.
    metadata = models.CharField(max_length=255, blank=True)

    class Meta:
        indexes = [models.Index(fields=["purpose", "user"])]

    def __str__(self):
        return f"{self.purpose} for {self.user_id}"

    @property
    def is_valid(self) -> bool:
        return self.used_at is None and self.expires_at > timezone.now()


class GuestAccess(models.Model):
    """An account created by sending a request without registering. It has
    no password; this permanent link (mailed to the owner) logs them in.
    Setting a password turns it into a regular account and removes the
    link."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="guest_access"
    )
    token = models.CharField(
        max_length=64, unique=True, editable=False, default=generate_public_token
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Guest access for {self.user_id}"


class GoogleAccount(TimeStampedModel):
    """Sign in with Google for this account. Keyed by Google's permanent
    account id (`sub`), never by address: a Google account may change its
    email, and the address alone must not decide whose account opens."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="google_account"
    )
    subject = models.CharField(max_length=255, unique=True)
    # The Google address at the last sign-in - shown in settings only.
    email = models.EmailField()
    last_login_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Google account of {self.user_id}"


class TwoFactor(TimeStampedModel):
    """Two-step verification with an authenticator app (TOTP, RFC 6238).
    A row exists only once the first code was confirmed - until then the
    secret lives in the session of the person setting it up."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="two_factor"
    )
    # The base32 secret, encrypted with the master key (documents'
    # encryption); plain only where no key is set (development).
    secret = models.TextField()
    secret_key_id = models.CharField(max_length=16, blank=True)
    # The last accepted 30-second step: a code works once, never replayed.
    last_step = models.BigIntegerField(default=0)
    # SHA-256 of each unused backup code.
    backup_codes = models.JSONField(default=list)
    # Part of every "remember this device" cookie; a new one forgets them all.
    device_nonce = models.CharField(max_length=64, default=generate_public_token)

    def __str__(self):
        return f"Two-step verification of {self.user_id}"


def is_guest_account(user) -> bool:
    return bool(user and user.is_authenticated and hasattr(user, "guest_access"))
