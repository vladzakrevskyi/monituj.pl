"""Asking account owners for a review on Trustpilot.

30 days after signing up an account gets one email "Oceń Monituj"; if the
link wasn't clicked, one more 30 days later - never more than MAX_EMAILS.
Whether someone actually left a review can't be known without Trustpilot's
paid API, so the click through our redirect counts as done. "Nie chcę
takich wiadomości" (also one-click from the mail app, List-Unsubscribe)
ends them for good.

Everyone gets the same email - Trustpilot doesn't allow asking only the
happy ones. The basis is our legitimate interest (Polityka prywatności),
so nothing goes before that version is in force: REVIEWS_SINCE."""

from datetime import date, timedelta

from django.conf import settings
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.common import legal
from apps.common.site import absolute_url
from apps.notifications.models import EmailTemplate, ReviewInvite
from apps.notifications.services import EmailService

REVIEWS_SINCE = date(2026, 10, 15)
FIRST_AFTER = timedelta(days=30)
AGAIN_AFTER = timedelta(days=30)
MAX_EMAILS = 2


def allowed():
    """The privacy policy saying we ask for reviews is in force."""
    return legal.in_force(legal.PRIVACY) and (
        legal.effective_date(legal.PRIVACY) >= REVIEWS_SINCE
    )


def due(now=None):
    """Accounts to ask now: confirmed, real, a month old - not asked yet, or
    asked over a month ago and silent since."""
    now = now or timezone.now()
    return (
        User.objects.filter(
            is_active=True,
            email_verified_at__isnull=False,
            date_joined__lte=now - FIRST_AFTER,
        )
        .exclude(demo_account__isnull=False)
        .filter(
            Q(review_invite__isnull=True)
            | Q(
                review_invite__sent_count__lt=MAX_EMAILS,
                review_invite__last_sent_at__lte=now - AGAIN_AFTER,
                review_invite__clicked_at__isnull=True,
                review_invite__declined_at__isnull=True,
            )
        )
        .order_by("pk")
    )


def links(invite):
    review = absolute_url(reverse("notifications:review", args=[invite.token]))
    stop = absolute_url(reverse("notifications:review-stop", args=[invite.token]))
    return review, stop


def send(user, invite=None):
    """One "Oceń Monituj" email. invite: to send without counting it (the
    sample for the team) - otherwise the user's own, counted."""
    counted = invite is None
    if counted:
        invite, _ = ReviewInvite.objects.get_or_create(user=user)
    review_url, stop_url = links(invite)
    EmailService.send(
        EmailTemplate.REVIEW_REQUEST,
        user.email,
        context={
            "review_url": review_url,
            "stop_url": stop_url,
            "again": invite.sent_count > 0,
        },
        headers={
            "List-Unsubscribe": f"<{stop_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )
    if counted:
        invite.sent_count += 1
        invite.last_sent_at = timezone.now()
        invite.save(update_fields=["sent_count", "last_sent_at"])


def send_due(now=None):
    """-> how many went."""
    if not allowed():
        return 0
    sent = 0
    for user in due(now).iterator():
        send(user)
        sent += 1
    return sent


def trustpilot_url():
    return settings.TRUSTPILOT_REVIEW_URL
