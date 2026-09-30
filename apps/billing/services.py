"""What an account's plan allows, and the one check that enforces it.

The limit is checked only when a request is about to go out (created,
confirmed from the no-account form, or reopened). Requests already in
progress are never stopped: reminders keep going and recipients keep
uploading, whatever happens to the plan."""

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import is_guest_account
from apps.billing import plans
from apps.billing.models import BillingAccount
from apps.common.exceptions import ApplicationError
from apps.demo.models import is_demo_user

# Stripe statuses that keep the paid plan. past_due: Stripe is still retrying
# the card - the account keeps working until it gives up and cancels.
PAID_STATUSES = {"active", "trialing", "past_due"}
PAST_DUE_GRACE = timedelta(days=14)


class PlanLimitError(ApplicationError):
    code = "PLAN_LIMIT_REACHED"
    status_code = 403


def stripe_mode():
    return settings.STRIPE_MODE


def trial_end_for(user):
    return user.date_joined + timedelta(days=plans.TRIAL_DAYS)


def account_for(user, lock=False):
    """The account's billing row, created on first use with the trial
    counted from registration. lock=True (inside a transaction) serializes
    limit checks, so two requests sent at once can't both take the last slot."""
    manager = BillingAccount.objects
    if lock:
        manager = manager.select_for_update()
    account = manager.filter(user=user).first()
    if account is None:
        account, _ = BillingAccount.objects.get_or_create(
            user=user, defaults={"trial_ends_at": trial_end_for(user)}
        )
        if lock:
            account = BillingAccount.objects.select_for_update().get(pk=account.pk)
    return account


def within_grace(status, past_due_since, now=None):
    """past_due counts as paid only for PAST_DUE_GRACE: whatever the retry
    settings in the Stripe dashboard, an unpaid plan doesn't last forever."""
    if status != "past_due":
        return True
    if past_due_since is None:
        return True
    return (now or timezone.now()) - past_due_since < PAST_DUE_GRACE


def is_subscribed(account):
    """A paid Stripe subscription in the current mode. A sandbox
    subscription means nothing once STRIPE_MODE=live, and the other way round."""
    return (
        account.stripe_mode == stripe_mode()
        and account.status in PAID_STATUSES
        and plans.PLANS.get(account.plan, plans.FREE).is_paid
        and within_grace(account.status, account.past_due_since)
    )


def customer_id(account):
    """The Stripe customer to use in the current mode, if there is one."""
    if account.stripe_mode == stripe_mode():
        return account.stripe_customer_id
    return ""


@dataclass
class PlanState:
    plan: plans.Plan
    # "subscription", "trial", "free" or "demo" (no limit)
    source: str
    used: int
    account: BillingAccount | None = None

    @property
    def limit(self):
        return None if self.source == "demo" else self.plan.active_requests

    @property
    def remaining(self):
        if self.limit is None:
            return None
        return max(self.limit - self.used, 0)

    @property
    def at_limit(self):
        return self.limit is not None and self.used >= self.limit

    @property
    def percent(self):
        if not self.limit:
            return 0
        return min(round(self.used * 100 / self.limit), 100)

    @property
    def trial_ends_at(self):
        return self.account.trial_ends_at if self.account else None

    @property
    def trial_days_left(self):
        if self.source != "trial" or self.trial_ends_at is None:
            return 0
        seconds = (self.trial_ends_at - timezone.now()).total_seconds()
        return max(int(-(-seconds // 86400)), 0)

    @property
    def is_subscribed(self):
        return self.source == "subscription"


def plan_for(user, account=None):
    """(plan, source) in force right now."""
    if is_demo_user(user):
        return plans.PRO, "demo"
    account = account or account_for(user)
    if is_subscribed(account):
        return plans.PLANS[account.plan], "subscription"
    # Passwordless accounts (from the no-account form) stay on Free; setting
    # a password makes them regular accounts, trial included.
    in_trial = account.trial_ends_at and timezone.now() < account.trial_ends_at
    if in_trial and not is_guest_account(user):
        return trial_plan_of(account), "trial"
    return plans.FREE, "free"


def state_for(user, account=None):
    from apps.requests.services import in_progress

    account = None if is_demo_user(user) else (account or account_for(user))
    plan, source = plan_for(user, account)
    return PlanState(
        plan=plan, source=source, used=in_progress(user).count(), account=account
    )


def limit_message(state):
    return (
        f"W planie {state.plan.name} możesz mieć jednocześnie "
        f"{plans.requests_phrase(state.limit)} w toku - tyle już masz. Zmień plan "
        "albo zamknij prośbę, na którą już nie czekasz."
    )


def check_request_allowed(owner, count=1):
    """Raises PlanLimitError when `count` more requests in progress would go
    over the plan. Call inside the transaction that sends the requests."""
    if is_demo_user(owner):
        return
    with transaction.atomic():
        account = account_for(owner, lock=True)
        state = state_for(owner, account)
        if state.at_limit:
            raise PlanLimitError(limit_message(state))
        if state.limit is not None and state.used + count > state.limit:
            free = state.limit - state.used
            raise PlanLimitError(
                f"W planie {state.plan.name} możesz mieć jednocześnie "
                f"{plans.requests_phrase(state.limit)} w toku - wolnych miejsc "
                f"zostało {free}, a wybrano {count} klientów. Wybierz mniej "
                "klientów albo zmień plan."
            )


def start_trial(sender, instance, created, raw=False, **kwargs):
    """Every new account starts with the trial - no card, no action needed."""
    if created and not raw:
        BillingAccount.objects.get_or_create(
            user=instance, defaults={"trial_ends_at": trial_end_for(instance)}
        )


# --- The plan picked on the pricing page ---------------------------------------

SIGNUP_PLAN_SESSION_KEY = "signup_plan"


def trial_plan_of(account):
    """The plan the account's trial is of."""
    plan = plans.PLANS.get(account.trial_plan or "")
    return plan if plan and plan.is_paid else plans.TRIAL_PLAN


def remember_signup_plan(request):
    """?plan=pro on the way to signing up (the pricing page buttons): kept in
    the session until the account exists - through the form, or Google."""
    code = request.GET.get("plan", "")
    plan = plans.PLANS.get(code)
    if plan and plan.is_paid:
        request.session[SIGNUP_PLAN_SESSION_KEY] = plan.code
    return signup_plan(request)


def signup_plan(request):
    if request is None or not hasattr(request, "session"):
        return None
    plan = plans.PLANS.get(request.session.get(SIGNUP_PLAN_SESSION_KEY, ""))
    return plan if plan and plan.is_paid else None


def apply_signup_plan(user, request):
    """A new account's trial is of the plan picked before signing up."""
    plan = signup_plan(request)
    if plan is None:
        return
    account = account_for(user)
    account.trial_plan = plan.code
    account.save(update_fields=["trial_plan", "updated_at"])
    request.session.pop(SIGNUP_PLAN_SESSION_KEY, None)


def welcome_url(request, user):
    """Where a brand new account lands: an account that picked a plan on the
    pricing page sees its plan and trial first; others the panel."""
    from django.contrib import messages
    from django.urls import reverse

    account = account_for(user)
    state = state_for(user, account)
    if not account.trial_plan or state.source != "trial":
        return reverse("accounts:panel")
    from apps.common.formatting import format_date

    messages.success(
        request,
        f"Masz {plans.TRIAL_DAYS} dni planu {state.plan.name} za darmo - do "
        f"{format_date(state.trial_ends_at)}. Potem wybierzesz plan albo konto "
        "przejdzie na bezpłatny Free.",
    )
    return reverse("billing:plan")
