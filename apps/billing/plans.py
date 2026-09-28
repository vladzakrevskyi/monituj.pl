"""Monituj plans.

A plan limits one thing: how many requests can be in progress at the same
time - sent, not closed and still waiting for documents. Reminders, clients
and every feature are the same on all plans, so someone with one request
never pays what an office with hundreds does, and nobody is charged for the
reminders that make the product work.

Prices are net amounts in grosze; VAT (settings.BILLING_VAT_RATE) is added
on top by Stripe. The Stripe prices are found by their lookup keys, so the
same code works in the sandbox and in live mode - `manage.py stripe_setup`
creates them."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

MONTH = "month"
YEAR = "year"
INTERVALS = (MONTH, YEAR)
TRIAL_DAYS = 30


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    active_requests: int
    monthly: int
    yearly: int
    tagline: str

    @property
    def is_paid(self):
        return self.monthly > 0

    def price(self, interval):
        return self.yearly if interval == YEAR else self.monthly


FREE = Plan("free", "Free", 3, 0, 0, "Na start i pojedyncze prośby.")
START = Plan(
    "start", "Start", 20, 3900, 39000, "Dla jednoosobowej firmy i małej kancelarii."
)
BIURO = Plan("biuro", "Biuro", 75, 8900, 89000, "Dla biura rachunkowego i działu kadr.")
PRO = Plan("pro", "Pro", 250, 17900, 179000, "Dla dużego biura z setkami klientów.")

PLANS = {plan.code: plan for plan in (FREE, START, BIURO, PRO)}
PAID_PLANS = (START, BIURO, PRO)
# New accounts use this plan for TRIAL_DAYS, without a card.
TRIAL_PLAN = BIURO


def lookup_key(plan, interval):
    return f"monituj_{plan.code}_{interval}"


def from_lookup_key(key):
    """(plan, interval) for a Stripe price lookup key, or None."""
    for plan in PAID_PLANS:
        for interval in INTERVALS:
            if lookup_key(plan, interval) == key:
                return plan, interval
    return None


def vat_rate():
    return int(settings.BILLING_VAT_RATE)


def gross(amount):
    """Net grosze -> gross grosze, rounded like an invoice line."""
    value = Decimal(amount) * (100 + vat_rate()) / 100
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def format_pln(amount):
    """3900 -> '39 zł', 4797 -> '47,97 zł', 123450 -> '1 234,50 zł'."""
    zloty, grosze = divmod(int(amount), 100)
    whole = f"{zloty:,}".replace(",", " ")
    if grosze:
        return f"{whole},{grosze:02d} zł"
    return f"{whole} zł"


def requests_phrase(count):
    """'3 prośby', '20 próśb', '1 prośbę' - as in 'możesz mieć ...'."""
    if count == 1:
        return "1 prośbę"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} prośby"
    return f"{count} próśb"
