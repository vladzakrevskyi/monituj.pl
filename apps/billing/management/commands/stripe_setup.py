"""Creates (or updates) in Stripe everything the plans need, in the mode
set by STRIPE_MODE: a product per paid plan, a monthly and a yearly price
(found later by lookup key), the VAT rate and the customer portal settings.
Safe to run again: existing objects are reused, and a changed price in
apps/billing/plans.py becomes a new Stripe price that takes over the lookup
key (subscriptions already running keep their old price until changed).

    python manage.py stripe_setup
    python manage.py stripe_setup --create-webhook   # on the server
"""

import stripe
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from apps.billing import gateway, plans
from apps.common.site import absolute_url

PRODUCT_DESCRIPTIONS = {
    plan.code: (
        f"Do {plans.requests_phrase(plan.active_requests)} w toku jednocześnie. "
        "Automatyczne przypomnienia i wszystkie funkcje Monituj."
    )
    for plan in plans.PAID_PLANS
}


def product_id(plan):
    return f"monituj_{plan.code}"


class Command(BaseCommand):
    help = "Creates Monituj products, prices, VAT and portal settings in Stripe."

    def add_arguments(self, parser):
        parser.add_argument(
            "--create-webhook",
            action="store_true",
            help="Also register <SITE_URL>/stripe/webhook/ (needs a public https "
            "SITE_URL) and print its signing secret.",
        )

    def handle(self, *args, **options):
        if not gateway.enabled():
            raise CommandError(
                f"STRIPE_{settings.STRIPE_MODE.upper()}_SECRET_KEY is empty."
            )
        stripe_client = gateway.client()
        self.stdout.write(f"Stripe: {settings.STRIPE_MODE}")
        product_ids = [self._product(stripe_client, plan) for plan in plans.PAID_PLANS]
        for plan in plans.PAID_PLANS:
            for interval in plans.INTERVALS:
                self._price(stripe_client, plan, interval)
        self._tax_rate(stripe_client)
        self._portal(stripe_client, product_ids)
        if options["create_webhook"]:
            self._webhook(stripe_client)
        gateway.clear_cache()
        self.stdout.write(self.style.SUCCESS("Gotowe."))

    def _product(self, stripe_client, plan):
        name = f"Monituj {plan.name}"
        params = {
            "name": name,
            "description": PRODUCT_DESCRIPTIONS[plan.code],
            "metadata": {"plan": plan.code},
        }
        try:
            product = stripe_client.v1.products.retrieve(product_id(plan))
        except stripe.InvalidRequestError:
            product = stripe_client.v1.products.create(
                params={"id": product_id(plan), **params}
            )
            self.stdout.write(f"  + produkt {name}")
            return product.id
        if (
            product.name != name
            or product.description != params["description"]
            or not product.active
        ):
            stripe_client.v1.products.update(
                product.id, params={**params, "active": True}
            )
            self.stdout.write(f"  ~ produkt {name}")
        return product.id

    def _price(self, stripe_client, plan, interval):
        key = plans.lookup_key(plan, interval)
        amount = plan.price(interval)
        existing = stripe_client.v1.prices.list(
            params={"lookup_keys": [key], "limit": 1}
        ).data
        if existing:
            price = existing[0]
            if (
                price.active
                and price.unit_amount == amount
                and price.currency == "pln"
                and price.recurring.interval == interval
                and price.tax_behavior == "exclusive"
            ):
                return price.id
        price = stripe_client.v1.prices.create(
            params={
                "product": product_id(plan),
                "currency": "pln",
                "unit_amount": amount,
                "recurring": {"interval": interval},
                "tax_behavior": "exclusive",
                "lookup_key": key,
                "transfer_lookup_key": True,
                "nickname": f"{plan.name} – "
                + ("rocznie" if interval == plans.YEAR else "miesięcznie"),
                "metadata": {"plan": plan.code, "interval": interval},
            }
        )
        if existing:
            stripe_client.v1.prices.update(existing[0].id, params={"active": False})
        self.stdout.write(f"  + cena {key}: {plans.format_pln(amount)} netto")
        return price.id

    def _tax_rate(self, stripe_client):
        rate = plans.vat_rate()
        if not rate:
            self.stdout.write("  VAT: 0% – bez stawki podatku")
            return None
        found = gateway.find_tax_rate(stripe_client, rate)
        if found:
            return found.id
        created = stripe_client.v1.tax_rates.create(
            params={
                "display_name": "VAT",
                "percentage": rate,
                "inclusive": False,
                "country": "PL",
                "jurisdiction": "PL",
                "tax_type": "vat",
                "metadata": {"monituj_vat": str(rate)},
            }
        )
        self.stdout.write(f"  + VAT {rate}%")
        return created.id

    def _portal(self, stripe_client, product_ids):
        prices = stripe_client.v1.prices.list(
            params={
                "lookup_keys": [
                    plans.lookup_key(plan, interval)
                    for plan in plans.PAID_PLANS
                    for interval in plans.INTERVALS
                ],
                "limit": 100,
            }
        ).data
        by_product = {}
        for price in prices:
            by_product.setdefault(price.product, []).append(price.id)
        business_profile = {"headline": "Monituj – plan i płatności"}
        # Stripe accepts only public addresses here.
        if settings.SITE_URL.startswith("https://"):
            business_profile["privacy_policy_url"] = absolute_url(
                reverse("legal:privacy")
            )
            business_profile["terms_of_service_url"] = absolute_url(
                reverse("legal:terms")
            )
        params = {
            "business_profile": business_profile,
            "default_return_url": absolute_url(reverse("billing:plan")),
            "features": {
                # Invoice details are changed (and checked) in Monituj, not
                # here - the VAT invoice is made from them.
                "customer_update": {"enabled": False},
                # The VAT invoice comes from inFakt (in the Monituj panel and by
                # email); Stripe's own "invoices" would only confuse.
                "invoice_history": {"enabled": False},
                "payment_method_update": {"enabled": True},
                "subscription_cancel": {
                    "enabled": True,
                    "mode": "at_period_end",
                    "proration_behavior": "none",
                },
                "subscription_update": {
                    "enabled": True,
                    "default_allowed_updates": ["price", "promotion_code"],
                    # Charge (or credit) the difference at once. With
                    # create_prorations Stripe would add it to the next
                    # renewal - after a switch to yearly, a year later.
                    "proration_behavior": "always_invoice",
                    "products": [
                        {"product": product, "prices": by_product.get(product, [])}
                        for product in product_ids
                        if by_product.get(product)
                    ],
                },
            },
            "metadata": {"monituj": "1"},
        }
        found = gateway.find_portal_configuration(stripe_client)
        if found:
            stripe_client.v1.billing_portal.configurations.update(
                found.id, params=params
            )
            self.stdout.write("  ~ portal klienta")
        else:
            stripe_client.v1.billing_portal.configurations.create(params=params)
            self.stdout.write("  + portal klienta")

    def _webhook(self, stripe_client):
        url = absolute_url(reverse("billing:webhook"))
        if not url.startswith("https://"):
            raise CommandError(
                f"Webhook needs a public https address, got {url}. Locally use: "
                "stripe listen --forward-to localhost:8000/stripe/webhook/"
            )
        for endpoint in stripe_client.v1.webhook_endpoints.list(
            params={"limit": 100}
        ).auto_paging_iter():
            if endpoint.url == url:
                stripe_client.v1.webhook_endpoints.update(
                    endpoint.id,
                    params={"enabled_events": sorted(gateway.HANDLED_EVENTS)},
                )
                self.stdout.write(
                    f"  ~ webhook {url} (już istnieje – sekret znajdziesz w "
                    "panelu Stripe)"
                )
                return
        endpoint = stripe_client.v1.webhook_endpoints.create(
            params={
                "url": url,
                "enabled_events": sorted(gateway.HANDLED_EVENTS),
                "description": "Monituj",
            }
        )
        env_name = f"STRIPE_{settings.STRIPE_MODE.upper()}_WEBHOOK_SECRET"
        self.stdout.write(f"  + webhook {url}")
        self.stdout.write(
            self.style.WARNING(f"  Wpisz do .env: {env_name}={endpoint.secret}")
        )
