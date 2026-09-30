import json
import logging
import re

import requests
import stripe
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import is_guest_account
from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.billing import gateway, invoicing, plans, registry
from apps.billing.forms import (
    COMPANY_FIELDS,
    EARLY_START_LABEL,
    BillingProfileForm,
    CheckoutForm,
    PlanChoiceForm,
    clean_nip,
)
from apps.billing.invoicing import valid_nip
from apps.billing.models import (
    BillingProfile,
    CheckoutConsent,
    VatInvoice,
    VatInvoiceStatus,
)
from apps.billing.services import account_for, customer_id, state_for
from apps.common import legal, throttle
from apps.common.exceptions import ApplicationError
from apps.common.responses import (
    ajax_form_error_response,
    error_response,
    success_response,
)
from apps.common.security import get_client_ip
from apps.consents.versions import wordings
from apps.demo.models import is_demo_user

logger = logging.getLogger("monituj")

CHECKOUT_SESSION_ID = re.compile(r"cs_(test|live)_[A-Za-z0-9]{10,200}")

# Each attempt creates a Checkout or portal session at Stripe.
STRIPE_SESSIONS_PER_HOUR = 20
# Re-reading the subscription on return from Stripe (a GET anyone logged in
# can repeat): beyond this the page just shows the stored state.
STRIPE_SYNCS_PER_HOUR = 30
INVOICE_DOWNLOADS_PER_HOUR = 60
GUEST_MESSAGE = "Ustaw hasło do konta, aby wybrać płatny plan."
PROFILE_MISSING_MESSAGE = (
    "Najpierw uzupełnij dane do faktury - bez nich nie możemy przyjąć płatności."
)
REGISTRY_LOOKUPS_PER_HOUR = 20
DEMO_MESSAGE = "Konto demonstracyjne nie może kupić planu."


def _pays_now(plan, interval, state):
    """Whether switching a subscription to this plan charges the card at
    once - the button then says so. A new interval starts a new period
    (paid now if yearly, credited if monthly); within one, a dearer plan
    costs the difference."""
    if state is None or not state.is_subscribed or state.account is None:
        return False
    current = plans.PLANS.get(state.account.plan, plans.FREE)
    if interval != state.account.interval:
        return interval == plans.YEAR
    return plan.price(interval) > current.price(interval)


def _price_rows(plan, state=None):
    rows = []
    for interval in plans.INTERVALS:
        net = plan.price(interval)
        gross = plans.gross(net)
        rows.append(
            {
                "interval": interval,
                "net": plans.format_pln(net),
                "gross": plans.format_pln(gross),
                # The yearly price per month, to compare with the monthly one.
                "per_month": plans.format_pln(net // 12),
                "per_month_gross": plans.format_pln(gross // 12),
                "pays_now": _pays_now(plan, interval, state),
            }
        )
    return rows


def _days(count):
    return "1 dzień" if count == 1 else f"{count} dni"


def plan_cards(state=None):
    """The plans as the pricing page and the panel show them."""
    return [
        {
            "plan": plan,
            "limit": plans.requests_phrase(plan.active_requests).split(" ", 1),
            "prices": _price_rows(plan, state),
            "current": state is not None
            and state.plan == plan
            and state.source in ("subscription", "free"),
            # Highlighted: the plan being tried, otherwise the recommended one.
            "trial": plan
            == (
                state.plan
                if state is not None and state.source == "trial"
                else plans.TRIAL_PLAN
            ),
        }
        for plan in plans.PLANS.values()
    ]


def _may_sync(request):
    """Counts one Stripe read for this user; False once over the limit."""
    key = f"stripe-sync:{request.user.pk}"
    if throttle.is_limited(key, STRIPE_SYNCS_PER_HOUR, throttle.HOUR):
        return False
    throttle.record(key)
    return True


def _may_download(request):
    key = f"invoice-pdf:{request.user.pk}"
    if throttle.is_limited(key, INVOICE_DOWNLOADS_PER_HOUR, throttle.HOUR):
        return False
    throttle.record(key)
    return True


def _blocked(request):
    """Why this account can't buy - or None."""
    if is_demo_user(request.user):
        return DEMO_MESSAGE
    if is_guest_account(request.user):
        return GUEST_MESSAGE
    return None


def _profile(user):
    return BillingProfile.objects.filter(user=user).first()


def _needs_profile(request):
    """Payments wait for checked invoice details: a refused invoice after
    the money is taken is what this prevents."""
    if _profile(request.user) is None:
        messages.error(request, PROFILE_MISSING_MESSAGE)
        return redirect(reverse("billing:plan") + "#dane")
    return None


def _to_stripe(request, make_url, error_message=gateway.UNAVAILABLE_MESSAGE):
    """Creates a Stripe session and sends the browser there - or back to the
    plan page with an explanation."""
    try:
        throttle.consume(
            f"stripe-session:{request.user.pk}", STRIPE_SESSIONS_PER_HOUR, throttle.HOUR
        )
        return redirect(make_url())
    except ApplicationError as exc:
        messages.error(request, exc.message)
    except stripe.StripeError:
        logger.exception("Stripe session failed")
        messages.error(request, error_message)
    return redirect("billing:plan")


@login_required
@require_GET
def plan_view(request):
    account = None if is_demo_user(request.user) else account_for(request.user)
    # Back from Stripe's "change plan" page: show the new plan right away
    # rather than after the webhook.
    if (
        request.GET.get("zmiana")
        and account
        and gateway.enabled()
        and _may_sync(request)
    ):
        try:
            account = gateway.refresh(account)
        except stripe.StripeError:
            logger.exception("Stripe refresh failed")
    state = state_for(request.user, account)
    blocked = _blocked(request)
    subscribed = state.is_subscribed
    return render(
        request,
        "billing/plan.html",
        {
            "state": state,
            "cards": plan_cards(state),
            "blocked": blocked,
            "can_buy": gateway.enabled()
            and not blocked
            and _profile(request.user) is not None,
            "yearly": subscribed and account.interval == plans.YEAR,
            # Left by a downgrade or a switch to monthly (gross).
            "credit": (
                plans.format_pln(account.credit)
                if account and customer_id(account) and account.credit
                else ""
            ),
            "current_price": (
                plans.format_pln(state.plan.price(account.interval))
                if subscribed
                else ""
            ),
            "trial_left": _days(state.trial_days_left),
            "has_customer": bool(account and customer_id(account)),
            "invoices": VatInvoice.objects.filter(user=request.user)[:24],
            "profile": _profile(request.user),
            "profile_form": BillingProfileForm(instance=_profile(request.user)),
            "payments_enabled": gateway.enabled(),
            "sandbox": not gateway.is_live(),
            "early_start_label": EARLY_START_LABEL,
            "free_plan": plans.FREE,
            "free_limit": plans.requests_phrase(plans.FREE.active_requests),
            "trial_plan": plans.TRIAL_PLAN,
            "trial_days": plans.TRIAL_DAYS,
            "vat_rate": plans.vat_rate(),
        },
    )


@login_required
@require_POST
def checkout(request):
    blocked = _blocked(request)
    if blocked:
        messages.error(request, blocked)
        return redirect("billing:plan")
    missing = _needs_profile(request)
    if missing:
        return missing
    state = state_for(request.user)
    if state.is_subscribed:
        # A second subscription would charge twice; switch the existing one.
        return change(request)
    form = CheckoutForm(request.POST)
    if not form.is_valid():
        messages.error(request, next(iter(form.errors.values()))[0])
        return redirect("billing:plan")
    plan, interval = form.chosen()

    def make_url():
        url = gateway.checkout_url(request.user, plan, interval)
        account = account_for(request.user)
        # The consumer's request to start at once, with the exact wording -
        # kept even after the account is deleted (see CheckoutConsent).
        CheckoutConsent.objects.create(
            user=request.user,
            email=request.user.email,
            stripe_mode=account.stripe_mode,
            stripe_customer_id=account.stripe_customer_id,
            plan=plan.code,
            interval=interval,
            text=EARLY_START_LABEL,
            documents=wordings(legal.CONTRACT),
            ip_address=get_client_ip(request) or None,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        )
        AuditService.log(
            AuditEvent.CHECKOUT_STARTED,
            actor=request.user,
            target=request.user,
            request=request,
            metadata={
                "plan": plan.code,
                "interval": interval,
                "early_start": True,
                "early_start_text": EARLY_START_LABEL,
            },
        )
        return url

    return _to_stripe(request, make_url)


@login_required
@require_POST
def change(request):
    blocked = _blocked(request)
    if blocked:
        messages.error(request, blocked)
        return redirect("billing:plan")
    missing = _needs_profile(request)
    if missing:
        return missing
    state = state_for(request.user)
    if not state.is_subscribed:
        return redirect("billing:plan")
    form = PlanChoiceForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Wybierz plan.")
        return redirect("billing:plan")
    plan, interval = form.chosen()
    account = state.account
    if (plan.code, interval) == (account.plan, account.interval):
        messages.info(request, "To jest Twój obecny plan.")
        return redirect("billing:plan")
    return _to_stripe(
        request, lambda: gateway.change_plan_url(request.user, plan, interval)
    )


@login_required
@require_POST
def portal(request):
    if is_demo_user(request.user):
        messages.error(request, DEMO_MESSAGE)
        return redirect("billing:plan")
    return _to_stripe(request, lambda: gateway.portal_url(request.user))


@login_required
@require_GET
def checkout_return(request):
    session_id = request.GET.get("session_id", "")
    account = None
    if (
        CHECKOUT_SESSION_ID.fullmatch(session_id)
        and gateway.enabled()
        and _may_sync(request)
    ):
        try:
            account = gateway.confirm_checkout(request.user, session_id)
        except stripe.StripeError:
            logger.exception("Stripe checkout confirmation failed")
    state = state_for(request.user)
    if account is not None and state.is_subscribed:
        messages.success(
            request,
            f"Dziękujemy! Plan {state.plan.name} jest aktywny. Fakturę wyślemy "
            "na Twój adres e-mail.",
        )
    else:
        messages.info(
            request,
            "Płatność jest przetwarzana - plan włączy się automatycznie w ciągu "
            "kilku minut.",
        )
    return redirect("billing:plan")


@csrf_exempt
@require_POST
def webhook(request):
    """Stripe's server calls this; only a valid signature is accepted."""
    try:
        event = gateway.parse_event(
            request.body, request.META.get("HTTP_STRIPE_SIGNATURE", "")
        )
    except ValueError:
        return HttpResponseBadRequest("invalid")
    try:
        gateway.handle_event(event)
    except stripe.StripeError, ApplicationError:
        # 5xx: Stripe retries later.
        logger.exception("Stripe webhook %s failed", event.id)
        return HttpResponse("retry", status=503)
    return HttpResponse("ok")


@login_required
@require_GET
def invoice_pdf(request, invoice_id):
    """The owner's VAT invoice PDF, fetched from inFakt."""
    invoice = VatInvoice.objects.filter(
        pk=invoice_id, user=request.user, status=VatInvoiceStatus.ISSUED
    ).first()
    if invoice is None:
        raise Http404
    if not _may_download(request):
        messages.error(request, "Zbyt wiele pobrań. Spróbuj ponownie za kilka minut.")
        return redirect("billing:plan")
    try:
        content = invoicing.pdf(invoice)
    except invoicing.InfaktError, requests.RequestException:
        logger.exception("inFakt PDF %s failed", invoice.pk)
        messages.error(
            request, "Nie udało się pobrać faktury. Spróbuj ponownie za chwilę."
        )
        return redirect("billing:plan")
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="{invoicing.pdf_filename(invoice)}"'
    )
    response["Cache-Control"] = "private, no-store"
    return response


@csrf_exempt
@require_POST
def infakt_webhook(request):
    """inFakt's server calls this. The body must be signed with the webhook's
    secret (x-infakt-signature); the activation request is answered with the
    same verification_code it carries."""
    if not invoicing.valid_signature(
        request.body, request.headers.get("X-Infakt-Signature", "")
    ):
        return HttpResponse("invalid signature", status=401)
    try:
        data = json.loads(request.body)
    except ValueError:
        return HttpResponseBadRequest("invalid")
    if not isinstance(data, dict):
        return HttpResponseBadRequest("invalid")
    if "verification_code" in data:
        return JsonResponse({"verification_code": str(data["verification_code"])})
    try:
        invoicing.handle_webhook(data)
    except invoicing.InfaktError, requests.RequestException:
        # The minute task checks the job anyway.
        logger.exception("inFakt webhook handling failed")
    return JsonResponse({"ok": True})


@login_required
@require_POST
def billing_profile(request):
    """Saves the invoice details (AJAX form on the plan page)."""
    blocked = _blocked(request)
    if blocked:
        return error_response("BLOCKED", blocked, status=403)
    # A Polish firm's NIP is checked in the Ministry of Finance register.
    checks_registry = request.POST.get("kind") == "company"
    if checks_registry and not _may_check_registry(request):
        return error_response(
            "RATE_LIMITED",
            "Zbyt wiele sprawdzeń NIP. Spróbuj ponownie za godzinę.",
            status=429,
        )
    profile = _profile(request.user)
    form = BillingProfileForm(request.POST, instance=profile)
    if not form.is_valid():
        return ajax_form_error_response(form)
    profile = form.save(commit=False)
    profile.user = request.user
    profile.save()
    account = account_for(request.user)
    if customer_id(account) and gateway.enabled():
        gateway.sync_customer(account, profile)
    messages.success(request, "Dane do faktury zapisane.")
    return success_response({"redirect_url": reverse("billing:plan") + "#dane"})


def _may_check_registry(request):
    key = f"nip-registry:{request.user.pk}"
    if throttle.is_limited(key, REGISTRY_LOOKUPS_PER_HOUR, throttle.HOUR):
        return False
    throttle.record(key)
    return True


@login_required
@require_POST
def registry_lookup(request):
    """The firm's official name and address for a NIP - fills the form."""
    nip = clean_nip(request.POST.get("nip", ""))
    if not valid_nip(nip):
        return error_response(
            "INVALID_NIP",
            "Ten NIP jest nieprawidłowy - sprawdź, czy nie ma literówki.",
            fields={"tax_id": ["Ten NIP jest nieprawidłowy."]},
        )
    if not _may_check_registry(request):
        return error_response(
            "RATE_LIMITED",
            "Zbyt wiele sprawdzeń NIP. Spróbuj ponownie za godzinę.",
            status=429,
        )
    try:
        found = registry.lookup(nip)
    except registry.FirmClosed:
        return error_response(
            "FIRM_CLOSED", "Według GUS ta firma zakończyła działalność."
        )
    except registry.InvalidNip:
        return error_response(
            "INVALID_NIP", "Ministerstwo Finansów nie zna tego NIP - sprawdź go."
        )
    if found is None:
        return error_response(
            "NOT_FOUND",
            "Nie znaleźliśmy tej firmy w rejestrach (albo są chwilowo "
            "niedostępne). Wpisz dane ręcznie.",
            status=404,
        )
    return success_response(
        {
            # Details the register has - locked on the form.
            "locked": [name for name, key in COMPANY_FIELDS.items() if found.get(key)],
            "company_name": found.get("name", ""),
            "street": found.get("street", ""),
            "post_code": found.get("post_code", ""),
            "city": found.get("city", ""),
            "status": found.get("status", ""),
            "source": found.get("source", ""),
        }
    )
