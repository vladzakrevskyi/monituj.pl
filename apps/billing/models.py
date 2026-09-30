from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class BillingAccount(TimeStampedModel):
    """An account's plan: its trial and, once it pays, a copy of its Stripe
    subscription (kept up to date by webhooks). Stripe stays the source of
    truth for money; this row only answers "what may this account do"."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="billing"
    )
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    # The plan picked on the pricing page before signing up - the trial is
    # of that plan. Empty: none picked, the trial is plans.TRIAL_PLAN.
    trial_plan = models.CharField(max_length=16, blank=True)
    # Which trial emails went out already ("7d", "1d", "ended").
    trial_notices = models.JSONField(default=list, blank=True)

    # The ids below exist only in this Stripe mode (sandbox or live); after
    # switching STRIPE_MODE they are ignored, never sent to the other mode.
    stripe_mode = models.CharField(max_length=8, blank=True)
    stripe_customer_id = models.CharField(max_length=64, blank=True, db_index=True)
    stripe_subscription_id = models.CharField(max_length=64, blank=True, db_index=True)
    plan = models.CharField(max_length=16, default="free")
    interval = models.CharField(max_length=8, blank=True)
    status = models.CharField(max_length=24, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    # Set when the subscription is cancelled but still paid for until then.
    cancel_at = models.DateTimeField(null=True, blank=True)
    # When the renewal payment first failed: the plan keeps working while
    # Stripe retries, but only for a limited time (services.PAST_DUE_GRACE).
    past_due_since = models.DateTimeField(null=True, blank=True)
    # The customer's credit in Stripe (gross grosze) - left by a downgrade or
    # a switch to monthly, used by the next payments first. Stripe's copy.
    credit = models.PositiveIntegerField(default=0)
    synced_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} - {self.plan} ({self.status or 'bez subskrypcji'})"


class StripeEvent(models.Model):
    """Webhook events already handled - Stripe may deliver one twice."""

    event_id = models.CharField(max_length=255, unique=True)
    type = models.CharField(max_length=64)
    livemode = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.type} {self.event_id}"


class BillingNotice(models.Model):
    """An email about payments waiting to go out. Sent by the
    send_billing_notices task within a minute - never inside a Stripe webhook,
    so a slow mail server can't hold Stripe up. user=None: an alert for the
    Monituj team (CONTACT_EMAIL), e.g. a refund or a dispute."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="billing_notices",
    )
    kind = models.CharField(max_length=32)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)

    def __str__(self):
        return f"{self.kind} ({self.user or 'zespół Monituj'})"


class CheckoutConsent(models.Model):
    """The buyer's request to start the service before the 14-day withdrawal
    period ends, with the exact wording shown. Kept after the account is
    deleted - like the invoices it belongs to - because it is what allows
    charging for the days used if a consumer withdraws."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checkout_consents",
    )
    email = models.EmailField()
    stripe_mode = models.CharField(max_length=8)
    stripe_customer_id = models.CharField(max_length=64, blank=True)
    plan = models.CharField(max_length=16)
    interval = models.CharField(max_length=8)
    text = models.TextField()
    # The contract's wording at the order: {document: {version, sha256}},
    # each archived in consents.LegalVersion - so the terms of a purchase
    # can be shown even after the account is gone.
    documents = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.email} - {self.plan} ({self.created_at:%Y-%m-%d})"


class VatInvoiceStatus(models.TextChoices):
    PENDING = "pending", "Do wystawienia"
    PROCESSING = "processing", "Wystawiana w inFakt"
    ISSUED = "issued", "Wystawiona"
    FAILED = "failed", "Błąd - wystaw ręcznie"


class VatInvoice(models.Model):
    """The Polish VAT invoice for one paid Stripe invoice, issued in inFakt.
    Created when Stripe reports the payment; the issue_invoices task then
    creates it in inFakt (asynchronously there), and emails the PDF. One per
    Stripe invoice (unique), so a repeated webhook never invoices twice.
    Kept after the account is deleted: invoices must be kept for 5 years."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vat_invoices",
    )
    email = models.EmailField()
    stripe_mode = models.CharField(max_length=8)
    stripe_invoice_id = models.CharField(max_length=64, unique=True)
    stripe_customer_id = models.CharField(max_length=64, blank=True)
    # What goes on the invoice, frozen at payment time.
    description = models.CharField(max_length=255)
    gross = models.PositiveIntegerField(help_text="Kwota brutto w groszach.")
    paid_at = models.DateTimeField()
    client = models.JSONField(default=dict)

    status = models.CharField(
        max_length=16,
        choices=VatInvoiceStatus.choices,
        default=VatInvoiceStatus.PENDING,
        db_index=True,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)
    infakt_mode = models.CharField(max_length=8, blank=True)
    infakt_task = models.CharField(max_length=64, blank=True, db_index=True)
    infakt_uuid = models.CharField(max_length=64, blank=True)
    number = models.CharField(max_length=64, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-paid_at"]

    def __str__(self):
        return self.number or f"{self.stripe_invoice_id} ({self.status})"

    @property
    def gross_display(self):
        from apps.billing.plans import format_pln

        return format_pln(self.gross)


class BillingProfileKind(models.TextChoices):
    PERSON = "person", "Osoba prywatna"
    COMPANY = "company", "Firma"


class BillingProfile(models.Model):
    """Who the VAT invoices are made out to - given and checked in Monituj
    before any payment (a Polish NIP must pass its checksum and the Ministry
    of Finance register), so inFakt never gets data it would refuse. Every
    invoice copies it at payment time; changes apply to the next ones."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="billing_profile",
    )
    kind = models.CharField(
        max_length=8,
        choices=BillingProfileKind.choices,
        default=BillingProfileKind.PERSON,
    )
    company_name = models.CharField(max_length=255, blank=True)
    tax_id = models.CharField(max_length=32, blank=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    street = models.CharField(max_length=255)
    post_code = models.CharField(max_length=16)
    city = models.CharField(max_length=100)
    # Buyers are in Poland only (for now).
    country = models.CharField(max_length=2, default="PL", editable=False)
    # What the Ministry of Finance register said about the NIP when saved.
    registry_name = models.CharField(max_length=255, blank=True)
    registry_status = models.CharField(max_length=32, blank=True)
    # Where the firm's details came from: "GUS", "MF" or "" (typed in), and
    # which of them the register had - those can't be changed by the buyer.
    registry_source = models.CharField(max_length=8, blank=True)
    registry_fields = models.JSONField(default=list, blank=True)
    registry_checked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.display_name

    @property
    def is_company(self):
        return self.kind == BillingProfileKind.COMPANY

    @property
    def display_name(self):
        if self.is_company:
            return self.company_name
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def address_line(self):
        return f"{self.street}, {self.post_code} {self.city}"

    def infakt_client(self):
        """The buyer as inFakt's invoice fields."""
        client = {
            "client_street": self.street,
            "client_city": self.city,
            "client_post_code": self.post_code,
            "client_country": self.country,
        }
        if self.is_company:
            client.update(
                client_business_activity_kind="other_business",
                client_company_name=self.company_name,
                client_tax_code=self.tax_id,
            )
        else:
            client.update(
                client_business_activity_kind="private_person",
                client_first_name=self.first_name,
                client_last_name=self.last_name,
            )
        return client
