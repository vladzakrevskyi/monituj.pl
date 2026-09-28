import logging
from datetime import timedelta

from celery import shared_task
from django.urls import reverse
from django.utils import timezone

from apps.billing import invoicing, notices, plans
from apps.billing.models import (
    BillingAccount,
    BillingNotice,
    CheckoutConsent,
    StripeEvent,
)
from apps.billing.services import is_subscribed, state_for, trial_plan_of
from apps.common.site import absolute_url
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService

logger = logging.getLogger("monituj")

# Stripe retries a webhook for up to three days; a month is plenty.
STRIPE_EVENT_RETENTION = timedelta(days=30)
NOTICE_RETENTION = timedelta(days=30)
# The early-start request is evidence for claims about the payment: kept
# as long as they can be brought (6 years under the Civil Code).
CONSENT_RETENTION = timedelta(days=6 * 365 + 2)
# An account whose trial ended long ago (before this code existed, or while
# the task was down) doesn't get a surprise "trial ended" email.
ENDED_NOTICE_WINDOW = timedelta(days=3)


def _notice_due(account, now):
    left = account.trial_ends_at - now
    if left <= timedelta(0):
        return "ended" if -left <= ENDED_NOTICE_WINDOW else None
    if left <= timedelta(days=1):
        return "1d"
    if left <= timedelta(days=7):
        return "7d"
    return None


def send_trial_notices(now=None):
    """Emails before the trial ends (7 days, 1 day) and when it has ended.
    Only for full accounts - not demo ones, and not passwordless accounts,
    which were never offered the trial on screen."""
    now = now or timezone.now()
    accounts = BillingAccount.objects.select_related("user").filter(
        trial_ends_at__isnull=False,
        trial_ends_at__lte=now + timedelta(days=7),
        trial_ends_at__gte=now - ENDED_NOTICE_WINDOW,
        user__is_active=True,
        user__email_verified_at__isnull=False,
        user__demo_account__isnull=True,
        user__guest_access__isnull=True,
    )
    sent = 0
    for account in accounts:
        notice = _notice_due(account, now)
        if notice is None or notice in account.trial_notices or is_subscribed(account):
            continue
        state = state_for(account.user, account)
        EmailService.send(
            EmailTemplate.TRIAL_ENDED
            if notice == "ended"
            else EmailTemplate.TRIAL_ENDING,
            to_email=account.user.email,
            context={
                "trial_plan": trial_plan_of(account).name,
                "free_limit": plans.requests_phrase(plans.FREE.active_requests),
                "free_plan": plans.FREE.name,
                "trial_ends_at": account.trial_ends_at,
                "tomorrow": notice == "1d",
                "in_progress": state.used,
                "over_free_limit": state.used > plans.FREE.active_requests,
                "plan_url": absolute_url(reverse("billing:plan")),
            },
        )
        # "1d" also covers "7d": a trial extended late shouldn't get both.
        account.trial_notices = sorted(
            {*account.trial_notices, notice, *(["7d"] if notice != "7d" else [])}
        )
        account.save(update_fields=["trial_notices", "updated_at"])
        sent += 1
    return sent


@shared_task
def daily():
    now = timezone.now()
    StripeEvent.objects.filter(received_at__lt=now - STRIPE_EVENT_RETENTION).delete()
    BillingNotice.objects.filter(sent_at__lt=now - NOTICE_RETENTION).delete()
    CheckoutConsent.objects.filter(created_at__lt=now - CONSENT_RETENTION).delete()
    # Paid Stripe invoices whose webhook never came still get a VAT invoice.
    try:
        invoicing.reconcile()
    except Exception:
        logger.exception("VAT invoice reconciliation failed")
    return send_trial_notices()


@shared_task
def issue_invoices():
    """VAT invoices in inFakt for paid Stripe invoices, then the emails."""
    return invoicing.process()


@shared_task
def send_notices():
    """Emails about plan changes and alerts for the team, queued by syncs
    with Stripe - within a minute, outside any webhook."""
    return notices.send_pending()
