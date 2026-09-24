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
    # The sender's zone when the request was created: reminders go out at
    # the clock time the request was sent (see apps.reminders.schedule).
    sender_timezone = models.CharField(max_length=64, default="Europe/Warsaw")

    # A request sent through the public form waits here until its sender
    # confirms it from their inbox; nothing reaches the recipient before.
    awaiting_confirmation = models.BooleanField(default=False)
    confirmation_token = models.CharField(
        max_length=64, unique=True, null=True, blank=True, editable=False
    )
    # The optional access password must be mailed to the recipient only
    # after confirmation, so it is kept here until then and cleared at once.
    pending_access_password = models.CharField(max_length=128, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

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

    @property
    def is_closed(self) -> bool:
        return self.closed_at is not None


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


class RecipientAccess(models.Model):
    """One permanent link per recipient email address, showing every request
    sent to that address - by any sender - in one place."""

    email = models.EmailField(unique=True)
    # The recipient's zone, learned when they open one of their links.
    timezone = models.CharField(max_length=64, blank=True)
    token = models.CharField(
        max_length=64, unique=True, editable=False, default=generate_public_token
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email
