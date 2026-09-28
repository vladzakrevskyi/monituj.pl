from django.contrib import admin
from django.db.models import Count

from apps.billing import plans
from apps.billing.models import (
    BillingAccount,
    BillingNotice,
    CheckoutConsent,
    StripeEvent,
    VatInvoice,
    VatInvoiceStatus,
)
from apps.billing.services import state_for
from apps.requests.models import Request


def over_limit_ids():
    """Accounts with more requests in progress than their plan allows. Over
    the limit is allowed (a rejected document reopens a finished request),
    but an account that stays far over it deserves a look."""
    candidates = (
        Request.objects.filter(awaiting_confirmation=False, closed_at__isnull=True)
        .values("created_by")
        .annotate(n=Count("id"))
        .filter(n__gt=plans.FREE.active_requests)
        .values_list("created_by", flat=True)
    )
    ids = []
    for account in BillingAccount.objects.filter(
        user_id__in=list(candidates)
    ).select_related("user"):
        state = state_for(account.user, account)
        if state.limit is not None and state.used > state.limit:
            ids.append(account.pk)
    return ids


class OverLimitFilter(admin.SimpleListFilter):
    title = "limit próśb"
    parameter_name = "limit"

    def lookups(self, request, model_admin):
        return [("ponad", "Ponad limit")]

    def queryset(self, request, queryset):
        if self.value() == "ponad":
            return queryset.filter(pk__in=over_limit_ids())
        return queryset


@admin.register(BillingAccount)
class BillingAccountAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "plan",
        "interval",
        "status",
        "trial_ends_at",
        "stripe_mode",
        "usage",
    ]
    list_filter = [OverLimitFilter, "plan", "status", "stripe_mode"]
    search_fields = ["user__email", "stripe_customer_id", "stripe_subscription_id"]
    # Only the trial is edited here: extend trial_ends_at (and empty
    # trial_notices, so the reminders go out again). The rest mirrors Stripe
    # and changes there - in the Stripe dashboard.
    readonly_fields = [
        "user",
        "stripe_mode",
        "stripe_customer_id",
        "stripe_subscription_id",
        "plan",
        "interval",
        "status",
        "current_period_end",
        "cancel_at",
        "past_due_since",
        "synced_at",
    ]

    @admin.display(description="W toku / limit")
    def usage(self, account):
        state = state_for(account.user, account)
        return f"{state.used} / {state.limit if state.limit is not None else '∞'}"


@admin.register(StripeEvent)
class StripeEventAdmin(admin.ModelAdmin):
    list_display = ["event_id", "type", "livemode", "received_at"]
    list_filter = ["type", "livemode"]
    readonly_fields = ["event_id", "type", "livemode", "received_at"]


@admin.register(BillingNotice)
class BillingNoticeAdmin(admin.ModelAdmin):
    list_display = ["kind", "user", "created_at", "sent_at"]
    list_filter = ["kind"]
    readonly_fields = ["user", "kind", "data", "created_at", "sent_at"]


@admin.register(CheckoutConsent)
class CheckoutConsentAdmin(admin.ModelAdmin):
    """Evidence - read only, removed automatically after 6 years."""

    list_display = ["email", "plan", "interval", "stripe_mode", "created_at"]
    search_fields = ["email", "stripe_customer_id"]
    readonly_fields = [f.name for f in CheckoutConsent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(VatInvoice)
class VatInvoiceAdmin(admin.ModelAdmin):
    """Invoices issued in inFakt for Stripe payments. A failed one: fix the
    cause (e.g. the buyer's data) and "Wystaw ponownie", or issue it by hand
    in inFakt."""

    list_display = ["number", "email", "gross", "status", "paid_at", "emailed_at"]
    list_filter = ["status", "stripe_mode"]
    search_fields = ["number", "email", "stripe_invoice_id", "infakt_uuid"]
    readonly_fields = [
        f.name for f in VatInvoice._meta.fields if f.name not in ("client",)
    ]
    actions = ["retry"]

    @admin.action(description="Wystaw ponownie (błędne)")
    def retry(self, request, queryset):
        updated = queryset.filter(status=VatInvoiceStatus.FAILED).update(
            status=VatInvoiceStatus.PENDING, attempts=0, error="", infakt_task=""
        )
        self.message_user(request, f"Ponownie w kolejce: {updated}.")

    def has_add_permission(self, request):
        return False
