"""Emails about the account's subscription: bought, changed, cancelled,
resumed, ended, payment failed - and alerts for the Monituj team (refunds,
disputes, a customer charged twice).

They follow the stored copy of the subscription, not Stripe events: whatever
path brings a change (webhook, return from Checkout or the portal), the
before/after comparison happens once, under a row lock, so each change is
queued exactly once. The queue (BillingNotice) is sent by a task every
minute. VAT invoices go out separately (invoicing.py).

The email about a new subscription also confirms the contract, as the
consumer rights act asks (art. 21): the terms, the request to start at
once and the right of withdrawal, with the Regulamin attached."""

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.billing import plans
from apps.billing.models import BillingNotice, CheckoutConsent
from apps.billing.services import PAID_STATUSES, stripe_mode, within_grace
from apps.common import legal
from apps.common.site import absolute_url
from apps.consents.services import version_in_force
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService

STARTED = "started"
UPGRADED = "upgraded"
DOWNGRADED = "downgraded"
INTERVAL = "interval"
CANCEL_SCHEDULED = "cancel_scheduled"
RESUMED = "resumed"
ENDED = "ended"
PAYMENT_FAILED = "payment_failed"
OPERATOR = "operator"

TEMPLATES = {
    STARTED: EmailTemplate.PLAN_STARTED,
    UPGRADED: EmailTemplate.PLAN_CHANGED,
    DOWNGRADED: EmailTemplate.PLAN_CHANGED,
    INTERVAL: EmailTemplate.PLAN_CHANGED,
    CANCEL_SCHEDULED: EmailTemplate.PLAN_CANCELLED,
    RESUMED: EmailTemplate.PLAN_RESUMED,
    ENDED: EmailTemplate.PLAN_ENDED,
    PAYMENT_FAILED: EmailTemplate.PAYMENT_FAILED,
    OPERATOR: EmailTemplate.BILLING_ALERT,
}


@dataclass(frozen=True)
class Snapshot:
    plan: str
    interval: str
    status: str
    cancel_at: object
    mode: str
    past_due_since: object = None

    @classmethod
    def of(cls, account):
        return cls(
            account.plan,
            account.interval,
            account.status,
            account.cancel_at,
            account.stripe_mode,
            account.past_due_since,
        )

    @property
    def paid(self):
        return (
            self.mode == stripe_mode()
            and self.status in PAID_STATUSES
            and plans.PLANS.get(self.plan, plans.FREE).is_paid
            and within_grace(self.status, self.past_due_since)
        )


def change_kind(before, after):
    """What happened between two snapshots, as one email-worthy change."""
    if before.paid and not after.paid:
        return ENDED
    if not after.paid:
        return None
    if not before.paid:
        return STARTED
    if before.plan != after.plan:
        old_limit = plans.PLANS[before.plan].active_requests
        new_limit = plans.PLANS[after.plan].active_requests
        return UPGRADED if new_limit > old_limit else DOWNGRADED
    if before.interval != after.interval:
        return INTERVAL
    if not before.cancel_at and after.cancel_at:
        return CANCEL_SCHEDULED
    if before.cancel_at and not after.cancel_at:
        return RESUMED
    if before.status != "past_due" and after.status == "past_due":
        return PAYMENT_FAILED
    return None


def _interval_label(interval):
    return "rocznie" if interval == plans.YEAR else "miesięcznie"


def _context(account, previous_plan, previous_interval, kind):
    from apps.billing.services import state_for

    plan = plans.PLANS.get(account.plan, plans.FREE)
    previous = plans.PLANS.get(previous_plan, plans.FREE)
    state = state_for(account.user, account)
    context = {
        "kind": kind,
        "plan_name": plan.name,
        "previous_plan_name": previous.name,
        "interval_label": _interval_label(account.interval),
        "previous_interval_label": _interval_label(previous_interval),
        "limit": plans.requests_phrase(plan.active_requests),
        "period_end": account.current_period_end,
        "cancel_at": account.cancel_at,
        "current_plan_name": state.plan.name,
        "current_limit": plans.requests_phrase(state.plan.active_requests),
        "free_plan": plans.FREE.name,
        "free_limit": plans.requests_phrase(plans.FREE.active_requests),
        "in_progress": state.used,
        "over_limit": state.limit is not None and state.used > state.limit,
        "over_free_limit": state.used > plans.FREE.active_requests,
        "plan_url": absolute_url(reverse("billing:plan")),
        "vat_rate": plans.vat_rate(),
        "to_yearly": account.interval == plans.YEAR,
        "credit": plans.format_pln(account.credit) if account.credit else "",
    }
    if plan.is_paid and account.interval:
        net = plan.price(account.interval)
        context["price"] = plans.format_pln(net)
        context["price_gross"] = plans.format_pln(plans.gross(net))
    return context


WITHDRAWAL_DAYS = 14


def _contract(notice):
    """The contract confirmation in the "plan started" email."""
    consent = (
        CheckoutConsent.objects.filter(user=notice.user).order_by("-created_at").first()
    )
    concluded = timezone.localdate(notice.created_at)
    return {
        "early_start_at": consent.created_at if consent else None,
        "withdraw_until": concluded + timedelta(days=WITHDRAWAL_DAYS),
        # The Terms in force when bought - and, during a notice period, the
        # day the announced new version applies (accepted on that day).
        "terms_version": legal.version_display(
            version_in_force(legal.TERMS) or legal.version(legal.TERMS)
        ),
        "terms_next": (
            legal.effective_date_display(legal.TERMS)
            if not legal.in_force(legal.TERMS)
            and version_in_force(legal.TERMS) is not None
            else ""
        ),
        "contract_email": settings.LEGAL_ENTITY.get("email") or settings.CONTACT_EMAIL,
        "withdrawal_url": absolute_url(reverse("legal:withdrawal")),
    }


def notify(account, before):
    """Queues an email to the owner about the change from `before` to the
    account's current state. Saved in the caller's transaction: a rolled
    back sync queues nothing."""
    kind = change_kind(before, Snapshot.of(account))
    if kind is None:
        return None
    BillingNotice.objects.create(
        user=account.user,
        kind=kind,
        data={"previous_plan": before.plan, "previous_interval": before.interval},
    )
    return kind


def dashboard_url(path):
    """A link into the Stripe dashboard in the current mode."""
    prefix = "" if settings.STRIPE_MODE == "live" else "test/"
    return f"https://dashboard.stripe.com/{prefix}{path}"


def alert_team(subject, lines, link="", key=""):
    """Queues an alert for the Monituj team. `key` makes it one-off: the
    same key never alerts twice."""
    if key and BillingNotice.objects.filter(kind=OPERATOR, data__key=key).exists():
        return None
    return BillingNotice.objects.create(
        kind=OPERATOR,
        data={"subject": subject, "lines": lines, "link": link, "key": key},
    )


def _send(notice):
    if notice.user is None:
        EmailService.send(
            TEMPLATES[OPERATOR],
            to_email=settings.CONTACT_EMAIL,
            context=notice.data,
        )
        return
    from apps.billing.services import account_for

    account = account_for(notice.user)
    context = _context(
        account,
        notice.data.get("previous_plan", ""),
        notice.data.get("previous_interval", ""),
        notice.kind,
    )
    attachments = None
    if notice.kind == STARTED:
        context.update(_contract(notice))
        attachments = [legal.contract_attachment()]
    EmailService.send(
        TEMPLATES[notice.kind],
        to_email=notice.user.email,
        context=context,
        attachments=attachments,
    )


def send_pending(limit=100):
    """Sends queued notices, oldest first. Each is marked sent in its own
    transaction, locked, so two workers never send one twice."""
    sent = 0
    for pk in (
        BillingNotice.objects.filter(sent_at__isnull=True)
        .order_by("created_at")
        .values_list("pk", flat=True)[:limit]
    ):
        with transaction.atomic():
            notice = (
                BillingNotice.objects.select_for_update(skip_locked=True, of=("self",))
                .select_related("user")
                .filter(pk=pk, sent_at__isnull=True)
                .first()
            )
            if notice is None:
                continue
            _send(notice)
            notice.sent_at = timezone.now()
            notice.save(update_fields=["sent_at"])
            sent += 1
    return sent
