"""VAT invoices for plan payments, issued in inFakt.

Stripe takes the money; the Polish VAT invoice comes from inFakt:

1. Stripe reports a paid invoice (webhook invoice.paid, or the hourly
   reconciliation) -> a VatInvoice row is queued with the buyer's details
   and the amount, frozen at that moment. Firms (a tax id given at checkout)
   get an invoice with their NIP, private persons one with their name.
2. The issue_invoices task (every minute) creates it in inFakt - an
   asynchronous job there - already marked paid by card, then checks the job
   (or inFakt's webhook reports it), and emails the PDF to the buyer.
3. The owner downloads it any time from "Plan i płatności".

Anything inFakt refuses lands in status "failed" and the team gets an alert:
such an invoice has to be issued by hand."""

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime, timedelta

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.billing import plans
from apps.billing.models import BillingAccount, VatInvoice, VatInvoiceStatus
from apps.common.site import absolute_url

logger = logging.getLogger("monituj")

TIMEOUT = 20
# Creating (or checking) keeps failing on network errors this many times
# before the team is asked to issue the invoice by hand.
MAX_ATTEMPTS = 10
# inFakt job codes (GET async/invoices/status).
JOB_CREATED = 201
JOB_FAILED = 422
RETRYABLE = (requests.RequestException, ValueError, KeyError)


class InfaktError(Exception):
    """inFakt refused the request (a 4xx other than auth) - retrying won't help."""


def mode():
    return settings.INFAKT_MODE


def keys(infakt_mode=None):
    return settings.INFAKT_KEYS[infakt_mode or mode()]


def enabled():
    return bool(keys()["api_key"])


def _request(method, path, infakt_mode=None, **kwargs):
    infakt_mode = infakt_mode or mode()
    response = requests.request(
        method,
        f"{settings.INFAKT_API_URLS[infakt_mode]}/{path}",
        headers={
            "X-inFakt-ApiKey": keys(infakt_mode)["api_key"],
            "Accept": "application/json",
        },
        timeout=TIMEOUT,
        **kwargs,
    )
    if response.status_code in (400, 404, 422):
        try:
            detail = json.dumps(response.json(), ensure_ascii=False)
        except ValueError:
            detail = response.text
        raise InfaktError(f"{response.status_code}: {detail[:500]}")
    # 401/403/429/5xx: configuration or a passing problem - retried.
    response.raise_for_status()
    return response


# --- 1. Queueing a paid Stripe invoice -------------------------------------------


def _stamp(value):
    return datetime.fromtimestamp(value, tz=UTC) if value else None


NIP_WEIGHTS = (6, 5, 7, 2, 3, 4, 5, 6, 7)


def valid_nip(nip):
    """Polish NIP: 10 digits, the last one a checksum. Stripe doesn't check
    it, inFakt refuses an invoice with a wrong one."""
    if len(nip) != 10 or not nip.isdigit():
        return False
    check = sum(int(d) * w for d, w in zip(nip, NIP_WEIGHTS, strict=False)) % 11
    return check != 10 and check == int(nip[9])


def _client(stripe_invoice):
    """Buyer details for inFakt from what the buyer typed in Stripe Checkout:
    with a tax id - a firm (NIP on the invoice), without - a private person."""
    address = stripe_invoice.get("customer_address") or {}
    street = " ".join(
        part for part in (address.get("line1"), address.get("line2")) if part
    )
    name = (stripe_invoice.get("customer_name") or "").strip() or (
        stripe_invoice.get("customer_email") or ""
    )
    country = (address.get("country") or "PL").upper()
    client = {
        "client_street": street,
        "client_city": address.get("city") or "",
        "client_post_code": address.get("postal_code") or "",
        "client_country": country,
    }
    tax_ids = stripe_invoice.get("customer_tax_ids") or []
    tax_id = ""
    if tax_ids:
        tax_id = (tax_ids[0].get("value") or "").replace(" ", "").replace("-", "")
        if country == "PL" and tax_id.upper().startswith("PL"):
            tax_id = tax_id[2:]
        if country == "PL" and not valid_nip(tax_id):
            # A typo at checkout: an invoice on the person is still valid;
            # the team is told, so the firm can get a corrected one.
            client["invalid_tax_id"] = tax_id
            tax_id = ""
    if tax_id:
        client.update(
            client_business_activity_kind="other_business",
            client_company_name=name,
            client_tax_code=tax_id,
        )
    else:
        first, _, last = name.partition(" ")
        client.update(
            client_business_activity_kind="private_person",
            client_first_name=first,
            client_last_name=last or first,
        )
    if country != "PL":
        client["sale_type"] = "service"
    return client


def _description(stripe_invoice):
    """One line for the invoice: the plan, monthly or yearly, and the period."""
    lines = [
        line
        for line in (stripe_invoice.get("lines") or {}).get("data", [])
        if line.get("amount", 0) > 0
    ]
    if not lines:
        return "Abonament Monituj"
    main = max(lines, key=lambda line: line.get("amount", 0))
    product = ((main.get("pricing") or {}).get("price_details") or {}).get(
        "product"
    ) or ""
    plan = plans.PLANS.get(product.removeprefix("monituj_"))
    start = min(_stamp(line["period"]["start"]) for line in lines)
    end = max(_stamp(line["period"]["end"]) for line in lines)
    yearly = (end - start) > timedelta(days=40)
    name = f"Abonament Monituj {plan.name if plan else ''}".strip()
    name += " (roczny)" if yearly else " (miesięczny)"
    if stripe_invoice.get("billing_reason") == "subscription_update":
        name = f"Dopłata za zmianę planu - {name}"
    start, end = timezone.localtime(start), timezone.localtime(end)
    return f"{name}, okres {start:%d.%m.%Y}-{end:%d.%m.%Y}"


def _buyer(account, stripe_invoice):
    """The checked invoice details from Monituj; what Stripe collected only
    for payments made before they existed."""
    from apps.billing.models import BillingProfile

    profile = (
        BillingProfile.objects.filter(user=account.user).first() if account else None
    )
    if profile is not None:
        return profile.infakt_client()
    return _client(stripe_invoice)


def queue_from_stripe(stripe_invoice):
    """Queues the VAT invoice for a paid Stripe invoice (a plain dict).
    Idempotent: the same Stripe invoice is queued once. Returns the row or
    None when nothing is to be invoiced (nothing was actually paid)."""
    if (
        stripe_invoice.get("status") != "paid"
        or (stripe_invoice.get("amount_paid") or 0) <= 0
        or (stripe_invoice.get("currency") or "").lower() != "pln"
    ):
        return None
    existing = VatInvoice.objects.filter(stripe_invoice_id=stripe_invoice["id"])
    if existing.exists():
        return existing.first()
    customer = stripe_invoice.get("customer") or ""
    account = (
        BillingAccount.objects.select_related("user")
        .filter(stripe_mode=settings.STRIPE_MODE, stripe_customer_id=customer)
        .first()
    )
    paid_at = (
        _stamp((stripe_invoice.get("status_transitions") or {}).get("paid_at"))
        or timezone.now()
    )
    email = stripe_invoice.get("customer_email") or (
        account.user.email if account else ""
    )
    try:
        with transaction.atomic():
            invoice = VatInvoice.objects.create(
                user=account.user if account else None,
                email=email,
                stripe_mode=settings.STRIPE_MODE,
                stripe_invoice_id=stripe_invoice["id"],
                stripe_customer_id=customer,
                description=_description(stripe_invoice)[:255],
                # What was actually paid: an amount settled from an earlier
                # credit was invoiced when that money came in.
                gross=stripe_invoice["amount_paid"],
                paid_at=paid_at,
                client=_buyer(account, stripe_invoice),
            )
            if invoice.client.get("invalid_tax_id"):
                _alert_invalid_nip(invoice)
            return invoice
    except IntegrityError:
        return VatInvoice.objects.get(stripe_invoice_id=stripe_invoice["id"])


def _alert_invalid_nip(invoice):
    from apps.billing import notices

    notices.alert_team(
        "Nieprawidłowy NIP przy płatności - faktura na osobę prywatną",
        [
            f"Klient: {invoice.email}",
            f"Podany NIP: {invoice.client['invalid_tax_id']}",
            "Faktura zostanie wystawiona na osobę prywatną. Jeśli to firma, "
            "ustal poprawny NIP i wystaw fakturę korygującą w inFakt.",
        ],
        key=f"vat-nip:{invoice.pk}",
    )


def reconcile(days=3):
    """Queues paid Stripe invoices of the last days that have no VAT invoice
    yet - covers webhooks that never arrived."""
    from apps.billing import gateway

    if not (gateway.enabled() and enabled()):
        return 0
    since = int((timezone.now() - timedelta(days=days)).timestamp())
    queued = 0
    known = set(
        VatInvoice.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=days + 1)
        ).values_list("stripe_invoice_id", flat=True)
    )
    for invoice in (
        gateway.client()
        .v1.invoices.list(
            params={"status": "paid", "created": {"gte": since}, "limit": 100}
        )
        .auto_paging_iter()
    ):
        if invoice.id in known:
            continue
        if queue_from_stripe(invoice.to_dict()):
            queued += 1
    return queued


# --- 2. Issuing in inFakt ---------------------------------------------------------


def _tax_symbol():
    rate = plans.vat_rate()
    return str(rate) if rate else "zw"


def _payload(invoice):
    day = timezone.localtime(invoice.paid_at).date().isoformat()
    body = {
        "invoice": {
            "status": "paid",
            "paid_date": day,
            "invoice_date": day,
            "sale_date": day,
            "payment_method": "card",
            "currency": "PLN",
            "notes": f"Zapłacono kartą przez Stripe ({invoice.stripe_invoice_id}).",
            **{k: v for k, v in invoice.client.items() if k.startswith("client_")},
            **(
                {"sale_type": invoice.client["sale_type"]}
                if "sale_type" in invoice.client
                else {}
            ),
            "services": [
                {
                    "name": invoice.description,
                    "tax_symbol": _tax_symbol(),
                    "quantity": 1,
                    # From the gross amount, so the invoice equals the
                    # payment to the grosz; inFakt works out net and VAT.
                    "gross_price": invoice.gross,
                }
            ],
        }
    }
    if settings.INFAKT_SEND_TO_KSEF:
        body["send_to_ksef"] = True
    return body


def _fail(invoice, error):
    from apps.billing import notices

    invoice.status = VatInvoiceStatus.FAILED
    invoice.error = str(error)[:2000]
    invoice.save(update_fields=["status", "error"])
    logger.error("VAT invoice %s failed: %s", invoice.pk, error)
    notices.alert_team(
        "Nie udało się wystawić faktury VAT w inFakt",
        [
            f"Klient: {invoice.email}",
            f"Kwota: {plans.format_pln(invoice.gross)} brutto, zapłacono "
            f"{timezone.localtime(invoice.paid_at):%d.%m.%Y}",
            f"Błąd: {invoice.error[:300]}",
            "Wystaw fakturę ręcznie w inFakt.",
        ],
        link=f"https://dashboard.stripe.com/"
        f"{'' if invoice.stripe_mode == 'live' else 'test/'}"
        f"invoices/{invoice.stripe_invoice_id}",
        key=f"vat-failed:{invoice.pk}",
    )


def _retry_later(invoice, error):
    invoice.attempts += 1
    invoice.error = str(error)[:2000]
    invoice.save(update_fields=["attempts", "error"])
    logger.warning(
        "VAT invoice %s: %s (attempt %s)", invoice.pk, error, invoice.attempts
    )
    if invoice.attempts >= MAX_ATTEMPTS:
        _fail(invoice, error)


def _email_failed(invoice, error):
    """The invoice exists in inFakt; only the email didn't go. Retried; in
    the end the team sends it by hand (it is in the panel anyway)."""
    from apps.billing import notices

    invoice.attempts += 1
    invoice.error = f"E-mail: {error}"[:2000]
    invoice.save(update_fields=["attempts", "error"])
    logger.warning("VAT invoice %s email failed: %s", invoice.pk, error)
    if invoice.attempts >= MAX_ATTEMPTS:
        notices.alert_team(
            "Faktura wystawiona, ale e-mail do klienta nie wyszedł",
            [
                f"Faktura: {invoice.number}",
                f"Klient: {invoice.email}",
                f"Błąd: {invoice.error[:300]}",
                "Wyślij fakturę z inFakt ręcznie - klient widzi ją też w panelu.",
            ],
            key=f"vat-email:{invoice.pk}",
        )


def _create(invoice):
    response = _request("POST", "async/invoices.json", json=_payload(invoice))
    data = response.json()
    invoice.infakt_mode = mode()
    invoice.infakt_task = data["invoice_task_reference_number"]
    invoice.status = VatInvoiceStatus.PROCESSING
    invoice.error = ""
    invoice.save(update_fields=["infakt_mode", "infakt_task", "status", "error"])


def _apply_job(invoice, job):
    """Applies an inFakt job result (status check or webhook)."""
    code = job.get("processing_code")
    if code == JOB_CREATED and job.get("invoice_uuid"):
        details = _request(
            "GET",
            f"invoices/{job['invoice_uuid']}.json",
            infakt_mode=invoice.infakt_mode,
        ).json()
        invoice.infakt_uuid = job["invoice_uuid"]
        invoice.number = details.get("number") or ""
        invoice.status = VatInvoiceStatus.ISSUED
        invoice.issued_at = timezone.now()
        invoice.error = ""
        # The email gets its own attempts.
        invoice.attempts = 0
        invoice.save(
            update_fields=[
                "infakt_uuid",
                "number",
                "status",
                "issued_at",
                "error",
                "attempts",
            ]
        )
    elif code == JOB_FAILED:
        _fail(invoice, job.get("invoice_errors") or job.get("processing_description"))


def _check(invoice):
    job = _request(
        "GET",
        f"async/invoices/status/{invoice.infakt_task}.json",
        infakt_mode=invoice.infakt_mode,
    ).json()
    _apply_job(invoice, job)


def pdf(invoice):
    """The invoice PDF from inFakt (original)."""
    return _request(
        "GET",
        f"invoices/{invoice.infakt_uuid}/pdf.json",
        infakt_mode=invoice.infakt_mode,
        params={"document_type": "original", "locale": "pl"},
    ).content


def pdf_filename(invoice):
    safe = "".join(ch if ch.isalnum() else "-" for ch in invoice.number or "faktura")
    return f"Faktura-{safe}.pdf"


def _email(invoice):
    from apps.notifications.models import EmailStatus, EmailTemplate
    from apps.notifications.services import EmailService

    log = EmailService.send(
        EmailTemplate.VAT_INVOICE,
        to_email=invoice.email,
        context={
            "number": invoice.number,
            "description": invoice.description,
            "gross": plans.format_pln(invoice.gross),
            "paid_at": invoice.paid_at,
            "plan_url": absolute_url(reverse("billing:plan")),
            "has_account": invoice.user_id is not None,
        },
        attachments=[(pdf_filename(invoice), pdf(invoice), "application/pdf")],
    )
    if log is not None and log.status == EmailStatus.FAILED:
        raise requests.ConnectionError("email not sent")
    invoice.emailed_at = timezone.now()
    invoice.save(update_fields=["emailed_at"])


def _step(invoice):
    if invoice.status == VatInvoiceStatus.PENDING:
        _create(invoice)
    elif invoice.status == VatInvoiceStatus.PROCESSING:
        _check(invoice)
    elif invoice.status == VatInvoiceStatus.ISSUED and invoice.emailed_at is None:
        _email(invoice)


def process(limit=50):
    """Moves every unfinished invoice one step: create -> check -> email.
    Each row is locked while it is worked on, so two workers never create
    the same invoice twice."""
    if not enabled():
        return 0
    todo = VatInvoice.objects.filter(
        status__in=[VatInvoiceStatus.PENDING, VatInvoiceStatus.PROCESSING]
    ) | VatInvoice.objects.filter(
        status=VatInvoiceStatus.ISSUED,
        emailed_at__isnull=True,
        attempts__lt=MAX_ATTEMPTS,
    )
    done = 0
    for pk in todo.order_by("created_at").values_list("pk", flat=True)[:limit]:
        with transaction.atomic():
            invoice = (
                VatInvoice.objects.select_for_update(skip_locked=True)
                .filter(pk=pk)
                .first()
            )
            if invoice is None or invoice.status == VatInvoiceStatus.FAILED:
                continue
            try:
                _step(invoice)
                done += 1
            except (
                InfaktError,
                requests.RequestException,
                ValueError,
                KeyError,
            ) as exc:
                if invoice.status == VatInvoiceStatus.ISSUED:
                    _email_failed(invoice, exc)
                elif isinstance(exc, InfaktError):
                    _fail(invoice, exc)
                else:
                    _retry_later(invoice, exc)
    return done


# --- inFakt webhooks --------------------------------------------------------------


def valid_signature(payload, signature):
    """x-infakt-signature: HMAC-SHA256 of the raw body, hex, with the
    webhook's secret key from inFakt."""
    secret = keys()["webhook_secret"]
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


def handle_webhook(data):
    """Speeds up step 2: the job result arrives instead of being polled."""
    event = (data.get("event") or {}).get("name")
    resource = data.get("resource") or {}
    if event not in ("async_invoice_creation_success", "async_invoice_creation_error"):
        return False
    task = resource.get("invoice_task_reference_number")
    if not task:
        return False
    with transaction.atomic():
        invoice = (
            VatInvoice.objects.select_for_update()
            .filter(infakt_task=task, status=VatInvoiceStatus.PROCESSING)
            .first()
        )
        if invoice is None:
            return False
        _apply_job(invoice, resource)
    return True
