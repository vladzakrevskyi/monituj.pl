"""Everything that talks to Stripe.

STRIPE_MODE decides which keys are used (sandbox or live). Payments happen
on Stripe's own pages - Checkout for the first order, the customer portal
for changing the plan, the card, invoices and cancelling - so no card data
ever touches Monituj. Webhooks keep BillingAccount in sync; every webhook
re-reads the customer's subscriptions from Stripe instead of trusting the
event body, so late or repeated events can't leave a stale state behind."""

import logging
import time
from datetime import UTC, datetime

import stripe
from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.billing import invoicing, notices, plans
from apps.billing.models import BillingAccount, StripeEvent, VatInvoice
from apps.billing.services import PAID_STATUSES, account_for, customer_id
from apps.common.exceptions import ApplicationError
from apps.common.site import absolute_url

logger = logging.getLogger("monituj")

HANDLED_EVENTS = {
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "customer.subscription.paused",
    "customer.subscription.resumed",
    "invoice.paid",
    "invoice.payment_failed",
    # Money going back: the plan doesn't change by itself, so the team is told.
    "charge.refunded",
    "charge.dispute.created",
}
EU_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU",
    "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES",
    "SE",
}  # fmt: skip
# Subscription statuses that can still charge the card.
LIVE_STATUSES = PAID_STATUSES | {"incomplete", "unpaid", "paused"}
UNAVAILABLE_MESSAGE = (
    "Płatności są chwilowo niedostępne. Spróbuj ponownie za kilka minut."
)
# Price and tax rate ids change only when `stripe_setup` runs.
CACHE_SECONDS = 300
_cache: dict = {}


class BillingUnavailableError(ApplicationError):
    code = "BILLING_UNAVAILABLE"
    status_code = 503


def keys():
    return settings.STRIPE_KEYS[settings.STRIPE_MODE]


def enabled():
    return bool(keys()["secret_key"])


def is_live():
    return settings.STRIPE_MODE == "live"


def client():
    if not enabled():
        raise BillingUnavailableError(UNAVAILABLE_MESSAGE)
    return stripe.StripeClient(keys()["secret_key"], max_network_retries=2)


def _cached(name, load):
    key = (settings.STRIPE_MODE, name)
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    value = load()
    _cache[key] = (time.monotonic() + CACHE_SECONDS, value)
    return value


def clear_cache():
    _cache.clear()


def price_ids():
    """{lookup_key: price id} for every paid plan and interval."""

    def load():
        wanted = [
            plans.lookup_key(plan, interval)
            for plan in plans.PAID_PLANS
            for interval in plans.INTERVALS
        ]
        found = client().v1.prices.list(
            params={"lookup_keys": wanted, "active": True, "limit": 100}
        )
        return {price.lookup_key: price.id for price in found.data}

    return _cached("prices", load)


def price_id(plan, interval):
    found = price_ids().get(plans.lookup_key(plan, interval))
    if not found:
        logger.error(
            "Stripe price %s missing - run manage.py stripe_setup",
            plans.lookup_key(plan, interval),
        )
        raise BillingUnavailableError(UNAVAILABLE_MESSAGE)
    return found


def _metadata(stripe_object):
    """Metadata as a plain dict - Stripe objects are not dicts."""
    metadata = getattr(stripe_object, "metadata", None)
    if metadata is None:
        return {}
    return metadata.to_dict() if hasattr(metadata, "to_dict") else dict(metadata)


def find_tax_rate(stripe_client, rate):
    for tax_rate in stripe_client.v1.tax_rates.list(
        params={"active": True, "limit": 100}
    ).auto_paging_iter():
        if _metadata(tax_rate).get("monituj_vat") == str(rate):
            return tax_rate
    return None


def tax_rate_id():
    """The VAT rate added to subscriptions, or None when VAT is 0."""
    rate = plans.vat_rate()
    if not rate:
        return None

    def load():
        found = find_tax_rate(client(), rate)
        if found is None:
            logger.error("Stripe VAT %s%% missing - run manage.py stripe_setup", rate)
            raise BillingUnavailableError(UNAVAILABLE_MESSAGE)
        return found.id

    return _cached(f"vat-{rate}", load)


def find_portal_configuration(stripe_client):
    for configuration in stripe_client.v1.billing_portal.configurations.list(
        params={"active": True, "limit": 100}
    ).auto_paging_iter():
        if _metadata(configuration).get("monituj") == "1":
            return configuration
    return None


def portal_configuration_id():
    def load():
        found = find_portal_configuration(client())
        return found.id if found else None

    return _cached("portal", load)


def _stamp(value):
    return datetime.fromtimestamp(value, tz=UTC) if value else None


# --- Customers and checkout ---------------------------------------------


def find_customers(user):
    """Stripe customers made for this user in the current mode - the stored
    one and any other with its user_id (e.g. from before an email change or
    a lost race)."""
    found = set()
    stored = customer_id(account_for(user))
    if stored:
        found.add(stored)
    for customer in (
        client()
        .v1.customers.list(params={"email": user.email, "limit": 100})
        .auto_paging_iter()
    ):
        if _metadata(customer).get("user_id") == str(user.pk):
            found.add(customer.id)
    return found


def _set_customer(account, customer):
    account.stripe_mode = settings.STRIPE_MODE
    account.stripe_customer_id = customer
    account.stripe_subscription_id = ""
    account.status = ""
    account.plan = plans.FREE.code
    account.interval = ""
    account.current_period_end = None
    account.cancel_at = None
    account.past_due_since = None
    account.save()


def ensure_customer(account):
    """The Stripe customer for this account in the current mode, created on
    first use. Locked, so two checkouts started at once (two tabs) share one
    customer - otherwise a payment could land on a customer Monituj doesn't
    know. Switching modes starts over: ids from the other mode stay out."""
    with transaction.atomic():
        account = (
            BillingAccount.objects.select_for_update()
            .select_related("user")
            .get(pk=account.pk)
        )
        existing = customer_id(account)
        if existing:
            return existing
        user = account.user
        # Reuse one made earlier for this user, if the id got lost.
        reused = next(iter(sorted(find_customers(user))), None)
        if reused is None:
            reused = (
                client()
                .v1.customers.create(
                    params={
                        "email": user.email,
                        "name": user.display_name or user.email,
                        "preferred_locales": ["pl"],
                        "metadata": {"user_id": str(user.pk)},
                    }
                )
                .id
            )
        _set_customer(account, reused)
        return reused


def sync_customer(account, profile):
    """Copies the checked invoice details to the Stripe customer, so Stripe's
    own payment documents match the VAT invoice. Best effort: the invoice
    itself is made from the profile, not from Stripe."""
    customer = customer_id(account)
    if not customer or profile is None:
        return
    stripe_client = client()
    try:
        stripe_client.v1.customers.update(
            customer,
            params={
                "name": profile.display_name,
                "address": {
                    "line1": profile.street,
                    "postal_code": profile.post_code,
                    "city": profile.city,
                    "country": profile.country,
                },
                "metadata": {"tax_id": profile.tax_id if profile.is_company else ""},
            },
        )
        existing = stripe_client.v1.customers.tax_ids.list(customer).data
        # Stripe's eu_vat covers EU firms; elsewhere the NIP is only on the
        # VAT invoice.
        wanted = (
            f"{profile.country}{profile.tax_id}"
            if profile.is_company and profile.country in EU_COUNTRIES
            else ""
        )
        for tax_id in existing:
            if tax_id.value != wanted:
                stripe_client.v1.customers.tax_ids.delete(customer, tax_id.id)
        if wanted and all(tax_id.value != wanted for tax_id in existing):
            stripe_client.v1.customers.tax_ids.create(
                customer, params={"type": "eu_vat", "value": wanted}
            )
    except stripe.StripeError:
        logger.warning("Stripe customer %s: invoice details not copied", customer)


def checkout_url(user, plan, interval):
    """A Stripe Checkout page for the first paid subscription. The invoice
    details were given (and checked) in Monituj already, so Checkout asks
    only for the card."""
    account = account_for(user)
    subscription_data = {"metadata": {"user_id": str(user.pk)}}
    tax_rate = tax_rate_id()
    if tax_rate:
        subscription_data["default_tax_rates"] = [tax_rate]
    customer = ensure_customer(account)
    sync_customer(account_for(user), getattr(user, "billing_profile", None))
    params = {
        "mode": "subscription",
        "customer": customer,
        "client_reference_id": str(user.pk),
        "line_items": [{"price": price_id(plan, interval), "quantity": 1}],
        "subscription_data": subscription_data,
        "metadata": {"user_id": str(user.pk), "plan": plan.code, "interval": interval},
        "locale": "pl",
        "allow_promotion_codes": True,
        "success_url": absolute_url(reverse("billing:return"))
        + "?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": absolute_url(reverse("billing:plan")),
    }
    session = client().v1.checkout.sessions.create(params=params)
    return session.url


def _portal_session(account, flow_data=None):
    params = {
        "customer": customer_id(account),
        # ?zmiana=1: the plan page re-reads the subscription on return, so a
        # change made in the portal shows at once, webhook or not.
        "return_url": absolute_url(reverse("billing:plan")) + "?zmiana=1",
        "locale": "pl",
    }
    configuration = portal_configuration_id()
    if configuration:
        params["configuration"] = configuration
    if flow_data:
        params["flow_data"] = flow_data
    return client().v1.billing_portal.sessions.create(params=params).url


def portal_url(user):
    """Stripe's page for invoices, the card, billing details and cancelling."""
    account = account_for(user)
    if not customer_id(account):
        raise BillingUnavailableError("Nie masz jeszcze płatnego planu.")
    return _portal_session(account)


def change_plan_url(user, plan, interval):
    """Stripe's confirmation page for switching an active subscription to
    another plan or interval (Stripe prorates the difference)."""
    account = account_for(user)
    subscription = client().v1.subscriptions.retrieve(account.stripe_subscription_id)
    item = subscription["items"]["data"][0]
    return _portal_session(
        account,
        flow_data={
            "type": "subscription_update_confirm",
            "subscription_update_confirm": {
                "subscription": subscription.id,
                "items": [
                    {
                        "id": item.id,
                        "price": price_id(plan, interval),
                        "quantity": 1,
                    }
                ],
            },
            "after_completion": {
                "type": "redirect",
                "redirect": {
                    "return_url": absolute_url(reverse("billing:plan")) + "?zmiana=1"
                },
            },
        },
    )


def close_customer(user):
    """The Stripe side of deleting an account, per Regulamin § 5a:
    - every subscription ends at once - Stripe is asked instead of trusting
      the local copy, which may lag behind, so nobody keeps paying for an
      account that no longer exists;
    - what was paid for the time left, plus any credit from a downgrade,
      goes back to the card;
    - the customer is stripped of personal data (name, email, address, NIP,
      cards). Payment records Stripe must keep stay with Stripe.
    A cancellation that fails raises (better a retry than charges for a
    deleted account); a refund or clean-up that fails only alerts the team,
    who finish it by hand. Returns the refunded gross grosze."""
    refunded = 0
    problems = []
    for customer in find_customers(user):
        unused = 0
        try:
            for subscription in (
                client()
                .v1.subscriptions.list(
                    params={"customer": customer, "status": "all", "limit": 100}
                )
                .auto_paging_iter()
            ):
                if subscription.status not in LIVE_STATUSES:
                    continue
                try:
                    client().v1.subscriptions.cancel(
                        subscription.id,
                        params={"cancellation_details": {"comment": DELETION_COMMENT}},
                    )
                except stripe.InvalidRequestError as exc:
                    # Already cancelled on Stripe's side.
                    if exc.code != "resource_missing":
                        raise
                    continue
                unused += unused_value(_plain(subscription), int(time.time()))
        finally:
            # Also when a later cancellation fails: a retry won't see the
            # subscriptions already cancelled, so their money goes back now.
            refunded += _return_money(
                customer, unused, problems, reason="account_deleted"
            )
        _anonymize(customer, problems)
    if refunded or problems:
        _alert_refund(
            user.email,
            refunded,
            problems,
            numbers=list(
                VatInvoice.objects.filter(user=user)
                .exclude(number="")
                .values_list("number", flat=True)[:3]
            ),
            why="Konto usunięte – zwrot za niewykorzystany okres",
            key=f"deletion:{user.pk}",
        )
    return refunded


# --- Money back ------------------------------------------------------------

# Marks the subscriptions ended by an account deletion, whose refund
# close_customer makes itself.
DELETION_COMMENT = "monituj: account deleted"


def _plain(stripe_object):
    return (
        stripe_object.to_dict()
        if hasattr(stripe_object, "to_dict")
        else dict(stripe_object)
    )


def unused_value(subscription, at):
    """Gross grosze paid for the rest of the current period at `at` (a unix
    time): the plan's price times the share of the period left. Upgrades are
    charged and downgrades credited as they happen, so the current plan's
    price is what the remaining time was paid at. Nothing when the period
    isn't paid (past_due and the like)."""
    if subscription["status"] != "active":
        return 0
    found = _plan_of(subscription)
    item = subscription["items"]["data"][0]
    start = item.get("current_period_start") or subscription.get("current_period_start")
    end = item.get("current_period_end") or subscription.get("current_period_end")
    if found is None or not start or not end or end <= start:
        return 0
    plan, interval = found
    left = min(max(end - at, 0), end - start)
    return round(plans.gross(plan.price(interval)) * left / (end - start))


def _refund(customer, amount, reason, key):
    """Sends `amount` grosze back to the customer, from the newest payments
    on. Returns how much went back - less when the payments don't cover
    it. Each refund is marked, so the webhook knows Monituj made it."""
    refunded = 0
    for charge in (
        client()
        .v1.charges.list(params={"customer": customer, "limit": 100})
        .auto_paging_iter()
    ):
        if refunded >= amount:
            break
        left = (charge.amount_captured or 0) - (charge.amount_refunded or 0)
        if not charge.paid or charge.status != "succeeded" or left <= 0:
            continue
        part = min(left, amount - refunded)
        client().v1.refunds.create(
            params={
                "charge": charge.id,
                "amount": part,
                "reason": "requested_by_customer",
                "metadata": {"monituj_reason": reason},
            },
            options={"idempotency_key": f"{key}-{charge.id}-{part}"},
        )
        refunded += part
    return refunded


def _return_money(customer, unused, problems, reason):
    """Refunds `unused` plus the customer's credit balance (left by a
    downgrade) and clears the refunded credit. Problems are collected for
    the team, never raised."""
    due = unused
    try:
        balance = client().v1.customers.retrieve(customer).balance or 0
        credit = max(-balance, 0)
        due = unused + credit
        if not due:
            return 0
        refunded = _refund(customer, due, reason, key=f"monituj-{reason}-{customer}")
        cleared = min(credit, refunded)
        if cleared:
            client().v1.customers.balance_transactions.create(
                customer,
                params={
                    "amount": cleared,
                    "currency": "pln",
                    "description": "Saldo zwrócone na kartę",
                },
            )
        if refunded < due:
            problems.append(
                f"Do zwrotu ręcznie: {plans.format_pln(due - refunded)} (klient "
                f"{customer}) – płatności w Stripe nie pokrywają tej kwoty."
            )
        return refunded
    except stripe.StripeError:
        logger.exception("Stripe refund for %s failed", customer)
        problems.append(
            f"Zwrot {plans.format_pln(due)} się nie udał (klient {customer}) – "
            "sprawdź w Stripe, ile już wróciło, i zwróć resztę ręcznie."
        )
        return 0


def _anonymize(customer, problems):
    """Removes the personal data Monituj put on a Stripe customer."""
    stripe_client = client()
    try:
        current = stripe_client.v1.customers.retrieve(customer)
        stripe_client.v1.customers.update(
            customer,
            params={
                "name": "",
                "email": "",
                "phone": "",
                "description": "",
                "address": "",
                "shipping": "",
                # An empty value removes a key; the date says why it's bare.
                "metadata": {
                    **{key: "" for key in _metadata(current)},
                    "monituj_deleted": timezone.localdate().isoformat(),
                },
            },
        )
        for tax_id in stripe_client.v1.customers.tax_ids.list(customer).data:
            stripe_client.v1.customers.tax_ids.delete(customer, tax_id.id)
        for method in stripe_client.v1.customers.payment_methods.list(
            customer
        ).auto_paging_iter():
            stripe_client.v1.payment_methods.detach(method.id)
    except stripe.StripeError:
        logger.exception("Stripe customer %s not anonymized", customer)
        problems.append(
            f"Nie udało się usunąć danych klienta {customer} w Stripe – usuń "
            "ręcznie imię, nazwę, e-mail, adres, NIP i karty."
        )


def _alert_refund(who, refunded, problems, numbers, why, key):
    lines = [f"Konto: {who}"]
    if refunded:
        lines.append(f"Zwrócono na kartę: {plans.format_pln(refunded)}.")
        lines.append(
            "Wystaw w inFakt fakturę korygującą"
            + (f" do faktury {', '.join(numbers)}." if numbers else ".")
        )
    notices.alert_team(why, lines + problems, key=key)


def _refund_credit_after_end(account, subscription):
    """A downgrade leaves credit for later payments. When the subscription
    ends with some of it unused, it goes back to the card (Regulamin § 5a)
    - unless another subscription still runs and uses it, or a deletion
    ended it (close_customer refunds those itself)."""
    details = subscription.get("cancellation_details") or {}
    if details.get("comment") == DELETION_COMMENT:
        return
    if account.status in LIVE_STATUSES:
        return
    problems = []
    refunded = _return_money(
        account.stripe_customer_id, 0, problems, reason="credit_after_end"
    )
    if refunded or problems:
        _alert_refund(
            account.user.email,
            refunded,
            problems,
            numbers=list(
                VatInvoice.objects.filter(user=account.user)
                .exclude(number="")
                .values_list("number", flat=True)[:3]
            ),
            why="Subskrypcja zakończona – zwrot niewykorzystanego salda",
            key=f"credit:{subscription.get('id')}",
        )


# --- Keeping the local copy in sync ----------------------------------------


def _plan_of(subscription):
    price = subscription["items"]["data"][0]["price"]
    found = plans.from_lookup_key(price.get("lookup_key") or "")
    if found:
        return found
    metadata = price.get("metadata") or {}
    plan = plans.PLANS.get(metadata.get("plan", ""))
    if plan and plan.is_paid:
        return plan, metadata.get("interval") or plans.MONTH
    return None


def _pick(subscriptions):
    """The subscription that counts: a paid one if there is one (the newest),
    otherwise the most recent of the rest."""
    ordered = sorted(subscriptions, key=lambda s: s["created"], reverse=True)
    for subscription in ordered:
        if subscription["status"] in PAID_STATUSES:
            return subscription
    return ordered[0] if ordered else None


def apply_subscription(account, subscription):
    """Stores a subscription (a plain dict, as Stripe sends it) - or its
    absence - on the account, and mails the owner what changed."""
    before = notices.Snapshot.of(account)
    old = (account.plan, account.interval, account.status, account.cancel_at)
    if subscription is None:
        account.stripe_subscription_id = ""
        account.status = ""
        account.plan = plans.FREE.code
        account.interval = ""
        account.current_period_end = None
        account.cancel_at = None
    else:
        found = _plan_of(subscription)
        if found is None:
            logger.error(
                "Stripe subscription %s has an unknown price", subscription["id"]
            )
            plan, interval = plans.FREE, ""
        else:
            plan, interval = found
        item = subscription["items"]["data"][0]
        period_end = _stamp(
            item.get("current_period_end") or subscription.get("current_period_end")
        )
        cancel_at = _stamp(subscription.get("cancel_at"))
        if cancel_at is None and subscription.get("cancel_at_period_end"):
            cancel_at = period_end
        account.stripe_subscription_id = subscription["id"]
        account.status = subscription["status"]
        account.plan = plan.code
        account.interval = interval
        account.current_period_end = period_end
        account.cancel_at = cancel_at
    if account.status != "past_due":
        account.past_due_since = None
    elif account.past_due_since is None:
        account.past_due_since = timezone.now()
    account.synced_at = timezone.now()
    account.save()
    now = (account.plan, account.interval, account.status, account.cancel_at)
    notices.notify(account, before)
    if now != old:
        AuditService.log(
            AuditEvent.PLAN_CHANGED,
            actor=account.user,
            target=account.user,
            metadata={
                "plan": account.plan,
                "interval": account.interval,
                "status": account.status,
                "cancel_at": account.cancel_at.isoformat() if account.cancel_at else "",
            },
        )
    return account


def refresh(account):
    """Reads the customer's subscriptions from Stripe and stores the one
    that counts."""
    # Locked while reading Stripe: two syncs at once (webhook and the return
    # page) apply one after another, each with fresh data, so no change is
    # mailed twice or undone by an older read.
    with transaction.atomic():
        account = (
            BillingAccount.objects.select_for_update()
            .select_related("user")
            .get(pk=account.pk)
        )
        customer = customer_id(account)
        if not customer:
            return account
        found = [
            subscription.to_dict()
            for subscription in client()
            .v1.subscriptions.list(
                params={"customer": customer, "status": "all", "limit": 20}
            )
            .data
        ]
        paid = sorted(s["id"] for s in found if s["status"] in PAID_STATUSES)
        if len(paid) > 1:
            # Charged twice for one account - one must be refunded by hand.
            logger.error("Stripe customer %s has %s paid subscriptions", customer, paid)
            notices.alert_team(
                "Klient płaci za kilka subskrypcji naraz",
                [
                    f"Konto: {account.user.email}",
                    f"Subskrypcje: {', '.join(paid)}",
                    "Anuluj zbędną subskrypcję i zwróć pieniądze w Stripe.",
                ],
                link=notices.dashboard_url(f"customers/{customer}"),
                key=f"double:{customer}:{','.join(paid)}",
            )
        return apply_subscription(account, _pick(found))


def confirm_checkout(user, session_id):
    """After returning from Checkout: don't wait for the webhook. The session
    must belong to this user - a session id in the URL proves nothing."""
    account = account_for(user)
    session = client().v1.checkout.sessions.retrieve(session_id)
    if session.client_reference_id != str(user.pk) or session.customer != customer_id(
        account
    ):
        return None
    return refresh(account)


# --- Webhooks ---------------------------------------------------------------


def parse_event(payload, signature):
    """Verifies Stripe's signature; raises ValueError for anything forged."""
    secret = keys()["webhook_secret"]
    if not secret:
        raise ValueError("webhook secret not configured")
    try:
        return stripe.Webhook.construct_event(payload, signature, secret)
    except stripe.SignatureVerificationError as exc:
        raise ValueError("invalid signature") from exc


def _account_for_event(data):
    customer = data.get("customer")
    if not customer:
        return None
    account = (
        BillingAccount.objects.select_related("user")
        .filter(stripe_mode=settings.STRIPE_MODE, stripe_customer_id=customer)
        .first()
    )
    return account or _adopt_customer(customer, data)


def _adopt_customer(customer, data):
    """A customer Monituj didn't store - e.g. a payment made through a
    Checkout page opened before a second one replaced the customer. Found by
    the user id Monituj put on the customer (or on the Checkout session); if
    that account's stored customer pays for nothing, this one takes over, so
    the payment is honored. Otherwise the team is alerted."""
    user_id = data.get("client_reference_id") or _metadata(
        client().v1.customers.retrieve(customer)
    ).get("user_id")
    if not str(user_id or "").isdigit():
        return None
    account = (
        BillingAccount.objects.select_for_update()
        .select_related("user")
        .filter(user_id=int(user_id))
        .first()
    )
    if account is None:
        return None
    stored = customer_id(account)
    if stored and stored != customer:
        stored_paid = any(
            s.status in PAID_STATUSES
            for s in client()
            .v1.subscriptions.list(params={"customer": stored, "status": "all"})
            .data
        )
        if stored_paid:
            notices.alert_team(
                "Płatność u drugiego klienta Stripe tego samego konta",
                [
                    f"Konto: {account.user.email}",
                    f"Zapisany klient: {stored}, płatność u: {customer}",
                    "Sprawdź, czy konto nie płaci podwójnie, i zwróć nadpłatę.",
                ],
                link=notices.dashboard_url(f"customers/{customer}"),
                key=f"adopt:{stored}:{customer}",
            )
            return None
    logger.warning("Stripe customer %s adopted by account %s", customer, account.pk)
    _set_customer(account, customer)
    return account


def _refunded_by_monituj(charge):
    """True when the charge's newest refund was made by Monituj itself (an
    account deletion, unused credit) - the team was told about it then."""
    try:
        latest = client().v1.refunds.list(params={"charge": charge, "limit": 1}).data
    except stripe.StripeError:
        return False
    return bool(latest) and bool(_metadata(latest[0]).get("monituj_reason"))


def _alert_money_back(event, account):
    data = event.data.object.to_dict()
    if event.type == "charge.refunded" and _refunded_by_monituj(data.get("id")):
        return
    if account is None and data.get("charge"):
        # A dispute names the charge, not the customer.
        customer = client().v1.charges.retrieve(data["charge"]).customer
        account = _account_for_event({"customer": customer}) if customer else None
    who = account.user.email if account else data.get("customer") or "nieznane"
    amount = plans.format_pln(data.get("amount_refunded") or data.get("amount") or 0)
    if event.type == "charge.refunded":
        subject = "Zwrot płatności w Stripe"
        what = (
            f"Zwrócono {amount}. Wystaw w inFakt fakturę korygującą. Plan "
            "klienta się nie zmienił"
        )
    else:
        subject = "Klient zakwestionował płatność (spór)"
        what = f"Spór o {amount}. Odpowiedz w Stripe w wyznaczonym terminie"
    notices.alert_team(
        subject,
        [
            f"Konto: {who}",
            f"{what} – jeśli trzeba, anuluj subskrypcję w Stripe.",
        ],
        link=notices.dashboard_url(f"payments/{data.get('payment_intent') or ''}"),
        key=f"{event.type}:{event.id}",
    )


def handle_event(event):
    """Returns True when the event changed something here."""
    if event.type not in HANDLED_EVENTS or bool(event.livemode) != is_live():
        return False
    with transaction.atomic():
        try:
            with transaction.atomic():
                StripeEvent.objects.create(
                    event_id=event.id, type=event.type, livemode=bool(event.livemode)
                )
        except IntegrityError:
            return False
        data = event.data.object.to_dict()
        if event.type == "invoice.paid":
            # The VAT invoice is due even if the account is gone meanwhile.
            invoicing.queue_from_stripe(data)
        account = _account_for_event(data)
        if event.type.startswith("charge."):
            _alert_money_back(event, account)
        if account is None:
            # A customer made outside Monituj, or an account deleted since.
            logger.warning("Stripe event %s for an unknown customer", event.id)
            return False
        # An error here rolls back the StripeEvent row, so Stripe retries.
        account = refresh(account)
        if event.type == "customer.subscription.deleted":
            _refund_credit_after_end(account, data)
    return True
