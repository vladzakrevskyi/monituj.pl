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
    # Sent to many clients at once: the invitation goes out from the queue
    # (send_queued_invitations, every minute), not inside the page request.
    invitation_queued = models.BooleanField(default=False, db_index=True)
    # Made by a recurring request (kept if that one is deleted: the history).
    recurring = models.ForeignKey(
        "RecurringRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requests",
    )
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


class RecurringInterval(models.TextChoices):
    DAILY = "daily", "Codziennie"
    WEEKLY = "weekly", "Co tydzień"
    BIWEEKLY = "biweekly", "Co 2 tygodnie"
    MONTHLY = "monthly", "Co miesiąc"


# month_day beyond the month's length means its last day; 31 = "ostatni dzień".
LAST_DAY_OF_MONTH = 31


class RecurringRequest(TimeStampedModel):
    """A request sent again and again to the same clients - every day, week,
    two weeks or month. Each run creates ordinary requests
    (RequestService.create_many), linked back here; this row keeps what to
    send, to whom and when (apps/requests/recurring.py)."""

    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="recurring_requests"
    )
    clients = models.ManyToManyField(Client, related_name="recurring_requests")
    # May hold {miesiąc} (the month before the sending day, "wrzesień 2026")
    # and {data} (the sending day, "01.10.2026").
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    item_names = models.JSONField(default=list)

    interval = models.CharField(
        max_length=16,
        choices=RecurringInterval.choices,
        default=RecurringInterval.MONTHLY,
    )
    # Monthly: the day of the month (29-31 in a shorter month: its last day).
    month_day = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(LAST_DAY_OF_MONTH)],
    )
    # Weekly and every two weeks: 0 = Monday ... 6 = Sunday.
    weekday = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(6)]
    )
    # Every two weeks: counted from this day (a day of `weekday`).
    anchor_on = models.DateField(null=True, blank=True)
    # Daily: working days only. Otherwise: a day off (weekend, Polish public
    # holiday) moves the sending to the next working day.
    workdays_only = models.BooleanField(default=True)
    # The deadline of each request: this many days after it is sent - or
    # the next such day of the month ("do 10. dnia miesiąca").
    deadline_days = models.PositiveSmallIntegerField(null=True, blank=True)
    deadline_month_day = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(LAST_DAY_OF_MONTH)],
    )

    reminders_enabled = models.BooleanField(default=True)
    first_reminder_after_days = models.PositiveSmallIntegerField(default=2)
    reminder_frequency_days = models.PositiveSmallIntegerField(default=3)
    max_reminders = models.PositiveSmallIntegerField(default=3)
    retention_days = models.PositiveSmallIntegerField(
        default=DEFAULT_RETENTION_DAYS,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_RETENTION_DAYS)],
    )

    active = models.BooleanField(default=True)
    # The next run: its day in the schedule, and the day it actually goes
    # out (later, when that day is off).
    next_due_on = models.DateField()
    next_run_on = models.DateField(db_index=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    # What the last run did: {"sent": 12} or {"skipped": "Brak wolnych..."}.
    last_result = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["next_run_on", "id"]

    def __str__(self):
        return f"{self.name} ({self.get_interval_display().lower()})"


class RequestTemplate(TimeStampedModel):
    """A saved pattern for new requests: what to ask for, the deadline and
    the settings - never the clients. Using it fills the new request form;
    the request keeps its own copy, so editing the template later changes
    nothing already sent (apps/requests/request_templates.py)."""

    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="request_templates"
    )
    # The template's own label in the picker, e.g. "Miesięczne - KPiR".
    title = models.CharField(max_length=120)
    # The request's name; may hold {miesiąc} and {data} like a recurring one.
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    item_names = models.JSONField(default=list)
    # One of the form's deadline buttons ("7", "14", "day10", "days",
    # "none"); "days" uses deadline_days.
    deadline_choice = models.CharField(max_length=8, default="14")
    deadline_days = models.PositiveSmallIntegerField(null=True, blank=True)

    reminders_enabled = models.BooleanField(default=True)
    first_reminder_after_days = models.PositiveSmallIntegerField(default=2)
    reminder_frequency_days = models.PositiveSmallIntegerField(default=3)
    max_reminders = models.PositiveSmallIntegerField(default=3)
    retention_days = models.PositiveSmallIntegerField(
        default=DEFAULT_RETENTION_DAYS,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_RETENTION_DAYS)],
    )
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["title", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "title"], name="unique_template_title_per_owner"
            )
        ]

    def __str__(self):
        return self.title
