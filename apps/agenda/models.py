"""The office's own memory (apps/agenda): reminders for oneself, the
calendar, the morning "Na dziś" email and a calendar feed for the phone."""

import secrets

from django.db import models

from apps.accounts.models import User
from apps.clients.models import Client


class PersonalReminder(models.Model):
    """ "Przypomnij mi" - zadzwonić do Kowalskiego 24.10. Belongs to the
    account (the team sees it on the calendar and the client's card); its
    author gets it in their morning email."""

    account = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="personal_reminders"
    )
    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Gone with the client: the text is usually about them.
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="personal_reminders",
    )
    text = models.CharField(max_length=300)
    due_on = models.DateField()
    done_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_on", "id"]
        indexes = [models.Index(fields=["account", "due_on"])]

    def __str__(self):
        return f"{self.due_on}: {self.text[:40]}"

    @property
    def is_done(self):
        return self.done_at is not None


def _feed_token():
    return secrets.token_urlsafe(32)


class AgendaSettings(models.Model):
    """Per person: the morning email, and the secret calendar-feed link."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="agenda")
    daily_email = models.BooleanField(default=True)
    daily_email_sent_on = models.DateField(null=True, blank=True)
    # The .ics link's secret - empty until the person asks for the link;
    # replaced when they ask for a new one (the old link stops working).
    feed_token = models.CharField(max_length=64, unique=True, null=True, blank=True)

    def __str__(self):
        return f"agenda of {self.user_id}"

    def new_feed_token(self):
        self.feed_token = _feed_token()
        self.save(update_fields=["feed_token"])
        return self.feed_token


def settings_for(user):
    found, _ = AgendaSettings.objects.get_or_create(user=user)
    return found
