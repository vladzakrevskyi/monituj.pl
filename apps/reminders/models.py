from django.db import models

from apps.accounts.models import User
from apps.common.models import TimeStampedModel
from apps.requests.models import Request


class ReminderKind(models.TextChoices):
    MANUAL = "manual", "Ręczne"
    AUTOMATIC = "automatic", "Automatyczne"


class Reminder(TimeStampedModel):
    request = models.ForeignKey(
        Request, on_delete=models.CASCADE, related_name="reminders"
    )
    kind = models.CharField(max_length=16, choices=ReminderKind.choices)
    sequence_number = models.PositiveSmallIntegerField(default=1)
    sent_at = models.DateTimeField(auto_now_add=True)
    triggered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="reminders_sent",
        null=True,
        blank=True,
    )

    class Meta:
        indexes = [models.Index(fields=["request", "kind"])]

    def __str__(self):
        return f"{self.kind} reminder for {self.request_id}"
