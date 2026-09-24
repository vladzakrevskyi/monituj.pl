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
    email_verified_at = models.DateTimeField(null=True, blank=True)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    privacy_policy_accepted_at = models.DateTimeField(null=True, blank=True)

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


def is_guest_account(user) -> bool:
    return bool(user and user.is_authenticated and hasattr(user, "guest_access"))
