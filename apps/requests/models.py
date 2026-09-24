from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.accounts.models import User
from apps.clients.models import Client
from apps.common.models import TimeStampedModel
from apps.common.security import generate_public_token

DEFAULT_RETENTION_DAYS = 90
MAX_RETENTION_DAYS = 365


class Request(TimeStampedModel):
    client = models.ForeignKey(
        Client, on_delete=models.PROTECT, related_name="requests"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="requests"
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    deadline = models.DateTimeField(null=True, blank=True)
    public_token = models.CharField(
        max_length=64, unique=True, editable=False, default=generate_public_token
    )

    reminders_enabled = models.BooleanField(default=True)
    first_reminder_after_days = models.PositiveSmallIntegerField(default=2)
    reminder_frequency_days = models.PositiveSmallIntegerField(default=3)
    max_reminders = models.PositiveSmallIntegerField(default=3)
    reminder_send_hour = models.PositiveSmallIntegerField(default=9)

    retention_days = models.PositiveSmallIntegerField(
        default=DEFAULT_RETENTION_DAYS,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_RETENTION_DAYS)],
        help_text="How long uploaded files are kept before anonymization.",
    )

    class Meta:
        indexes = [
            models.Index(fields=["client"]),
            models.Index(fields=["public_token"]),
        ]

    def __str__(self):
        return self.name

    @property
    def is_password_protected(self) -> bool:
        return hasattr(self, "password_protected_access")


class RequestItemStatus(models.TextChoices):
    BRAK = "brak", "Brak"
    W_TRAKCIE = "w_trakcie", "W trakcie"
    DOSTARCZONY = "dostarczony", "Dostarczony"
    ZAAKCEPTOWANY = "zaakceptowany", "Zaakceptowany"
    ODRZUCONY = "odrzucony", "Odrzucony"


class RequestItem(TimeStampedModel):
    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=32,
        choices=RequestItemStatus.choices,
        default=RequestItemStatus.BRAK,
    )
    rejection_reason = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["request", "status"])]

    def __str__(self):
        return self.name


class PasswordProtectedAccess(TimeStampedModel):
    request = models.OneToOneField(
        Request, on_delete=models.CASCADE, related_name="password_protected_access"
    )
    password_hash = models.CharField(max_length=255)

    def __str__(self):
        return f"Password protection for {self.request_id}"


class AnonymousRequestThrottle(TimeStampedModel):
    """One row per IP per calendar day, reserved atomically to limit
    unauthenticated request creation (the no-account "wyślij prośbę" flow)
    to once a day - keyed by a hash of the IP, not a cookie/session, so it
    can't be reset by an incognito window."""

    ip_hash = models.CharField(max_length=64)
    throttle_date = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["ip_hash", "throttle_date"],
                name="unique_anonymous_request_per_day",
            )
        ]
