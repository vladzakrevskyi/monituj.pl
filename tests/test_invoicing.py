import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest
import requests
import stripe
from django.core import mail
from django.urls import reverse

from apps.accounts.models import User
from apps.billing import invoicing
from apps.billing.models import VatInvoice, VatInvoiceStatus
from apps.billing.notices import send_pending
from apps.billing.services import account_for
from tests.conftest import page_text
from tests.test_billing import _event, _post_webhook, fake_stripe  # noqa: F401

WEBHOOK_SECRET = "infakt-secret"
PAID_AT = 1_790_590_000  # 28.09.2026


def stripe_invoice(
    invoice_id="in_1",
    customer="cus_1",
    name="Jan Kowalski",
    tax_ids=None,
    amount=10947,
    reason="subscription_create",
    days=30,
    **extra,
):
    return {
        "id": invoice_id,
        "object": "invoice",
        "status": "paid",
        "amount_paid": amount,
        "currency": "pln",
        "customer": customer,
        "customer_email": "owner@example.com",
        "customer_name": name,
        "customer_address": {
            "line1": "ul. Prosta 1",
            "line2": "m. 2",
            "city": "Warszawa",
            "postal_code": "00-001",
            "country": "PL",
        },
        "customer_tax_ids": tax_ids or [],
        "billing_reason": reason,
        "status_transitions": {"paid_at": PAID_AT},
        "lines": {
            "data": [
                {
                    "amount": 8900,
                    "period": {"start": PAID_AT, "end": PAID_AT + days * 86400},
                    "pricing": {
                        "price_details": {"product": "monituj_biuro", "price": "p"}
                    },
                }
            ]
        },
        **extra,
    }


class FakeInfakt:
    """Answers like api.sandbox-infakt.pl and records every call."""

    def __init__(self):
        self.calls = []
        self.create_status = 201
        self.job = {"processing_code": 201, "invoice_uuid": "uuid-1"}
        self.down = False

    def __call__(self, method, url, headers=None, timeout=None, **kwargs):
        self.calls.append((method, url, kwargs, headers))
        if self.down:
            raise requests.ConnectionError("down")
        path = url.split("/api/v3/", 1)[1]
        if method == "POST" and path == "async/invoices.json":
            if self.create_status == 422:
                return _response(422, {"errors": {"client_tax_code": ["zły NIP"]}})
            return _response(
                201,
                {"invoice_task_reference_number": "task-1", "processing_code": 100},
            )
        if path == "async/invoices/status/task-1.json":
            return _response(200, self.job)
        if path == "invoices/uuid-1.json":
            return _response(200, {"uuid": "uuid-1", "number": "7/09/2026"})
        if path == "invoices/uuid-1/pdf.json":
            return _response(200, content=b"%PDF-1.4 faktura")
        return _response(404, {})

    def created_payload(self):
        return next(
            k["json"] for m, u, k, h in self.calls if u.endswith("async/invoices.json")
        )


def _response(status, data=None, content=b""):
    def raise_for_status():
        if status >= 400:
            raise requests.HTTPError(str(status))

    return SimpleNamespace(
        status_code=status,
        text=json.dumps(data or {}),
        json=lambda: data,
        content=content or json.dumps(data or {}).encode(),
        raise_for_status=raise_for_status,
    )


@pytest.fixture
def infakt(settings, monkeypatch):
    settings.INFAKT_KEYS = {
        "sandbox": {"api_key": "sandbox-key", "webhook_secret": WEBHOOK_SECRET},
        "live": {"api_key": "", "webhook_secret": ""},
    }
    fake = FakeInfakt()
    monkeypatch.setattr(requests, "request", fake)
    return fake


def _customer(user):
    account = account_for(user)
    account.stripe_mode, account.stripe_customer_id = "sandbox", "cus_1"
    account.save()
    return account


def _run_until_done(times=3):
    for _ in range(times):
        invoicing.process()


# --- Queueing ---------------------------------------------------------------------


@pytest.mark.django_db
def test_private_person_gets_an_invoice_on_their_name(user):
    _customer(user)

    invoice = invoicing.queue_from_stripe(stripe_invoice())

    assert invoice.user == user
    assert invoice.gross == 10947
    assert invoice.client == {
        "client_street": "ul. Prosta 1 m. 2",
        "client_city": "Warszawa",
        "client_post_code": "00-001",
        "client_country": "PL",
        "client_business_activity_kind": "private_person",
        "client_first_name": "Jan",
        "client_last_name": "Kowalski",
    }
    assert invoice.description == (
        "Abonament Monituj Biuro (miesięczny), okres 28.09.2026-28.10.2026"
    )


@pytest.mark.django_db
def test_firm_with_nip_gets_an_invoice_on_the_firm(user):
    invoice = invoicing.queue_from_stripe(
        stripe_invoice(
            name="Biuro Rachunkowe Sp. z o.o.",
            tax_ids=[{"type": "eu_vat", "value": "PL 521-301-72-28"}],
            days=365,
            reason="subscription_update",
        )
    )

    assert invoice.client["client_business_activity_kind"] == "other_business"
    assert invoice.client["client_company_name"] == "Biuro Rachunkowe Sp. z o.o."
    assert invoice.client["client_tax_code"] == "5213017228"
    assert "client_first_name" not in invoice.client
    assert invoice.description.startswith(
        "Dopłata za zmianę planu - Abonament Monituj Biuro (roczny)"
    )


@pytest.mark.django_db
def test_nothing_paid_means_no_invoice_and_repeats_are_ignored(user):
    assert invoicing.queue_from_stripe(stripe_invoice(amount=0)) is None
    assert invoicing.queue_from_stripe(stripe_invoice(status="open")) is None

    first = invoicing.queue_from_stripe(stripe_invoice())
    again = invoicing.queue_from_stripe(stripe_invoice())

    assert first.pk == again.pk
    assert VatInvoice.objects.count() == 1


@pytest.mark.django_db
def test_paid_stripe_invoice_webhook_queues_the_vat_invoice(
    client,
    user,
    fake_stripe,  # noqa: F811
):
    fake_stripe.subscriptions = []
    payload = json.loads(_event("invoice.paid", customer="cus_unknown"))
    payload["data"]["object"] = stripe_invoice(customer="cus_unknown")
    fake_stripe.v1.customers.retrieve.return_value = stripe.StripeObject.construct_from(
        {"id": "cus_unknown", "metadata": {}}, "k"
    )

    response = _post_webhook(client, json.dumps(payload))

    assert response.status_code == 200
    # Due even though no account matches (e.g. deleted since).
    invoice = VatInvoice.objects.get()
    assert invoice.user is None
    assert invoice.email == "owner@example.com"


# --- Issuing ----------------------------------------------------------------------


@pytest.mark.django_db
def test_invoice_is_created_paid_by_card_and_emailed_with_the_pdf(user, infakt):
    _customer(user)
    invoicing.queue_from_stripe(stripe_invoice())

    _run_until_done()

    invoice = VatInvoice.objects.get()
    assert invoice.status == VatInvoiceStatus.ISSUED
    assert invoice.number == "7/09/2026"
    assert invoice.emailed_at is not None
    body = infakt.created_payload()
    assert "send_to_ksef" not in body
    data = body["invoice"]
    assert data["status"] == "paid"
    assert data["payment_method"] == "card"
    assert data["paid_date"] == data["sale_date"] == "2026-09-28"
    assert data["client_first_name"] == "Jan"
    assert data["services"] == [
        {
            "name": invoice.description,
            "tax_symbol": "23",
            "quantity": 1,
            "gross_price": 10947,
        }
    ]
    assert infakt.calls[0][3]["X-inFakt-ApiKey"] == "sandbox-key"
    assert "api.sandbox-infakt.pl" in infakt.calls[0][1]
    message = mail.outbox[-1]
    assert message.subject == "Faktura VAT 7/09/2026 - Monituj"
    assert message.to == ["owner@example.com"]
    assert message.attachments[0][0] == "Faktura-7-09-2026.pdf"
    assert message.attachments[0][1] == b"%PDF-1.4 faktura"


@pytest.mark.django_db
def test_vat_exempt_seller_and_ksef(settings, user, infakt):
    settings.BILLING_VAT_RATE = 0
    settings.INFAKT_SEND_TO_KSEF = True
    invoicing.queue_from_stripe(stripe_invoice())

    invoicing.process()

    body = infakt.created_payload()
    assert body["invoice"]["services"][0]["tax_symbol"] == "zw"
    assert body["send_to_ksef"] is True


@pytest.mark.django_db
def test_refused_invoice_alerts_the_team(settings, user, infakt):
    infakt.create_status = 422
    invoicing.queue_from_stripe(stripe_invoice())

    invoicing.process()
    send_pending()

    invoice = VatInvoice.objects.get()
    assert invoice.status == VatInvoiceStatus.FAILED
    assert "zły NIP" in invoice.error
    alert = mail.outbox[-1]
    assert alert.to == [settings.CONTACT_EMAIL]
    assert "Nie udało się wystawić faktury" in alert.subject


@pytest.mark.django_db
def test_failed_job_in_infakt_is_reported(user, infakt):
    infakt.job = {"processing_code": 422, "invoice_errors": {"base": ["błąd"]}}
    invoicing.queue_from_stripe(stripe_invoice())

    _run_until_done()

    assert VatInvoice.objects.get().status == VatInvoiceStatus.FAILED


@pytest.mark.django_db
def test_network_problems_are_retried_then_reported(user, infakt):
    infakt.down = True
    invoicing.queue_from_stripe(stripe_invoice())

    invoicing.process()
    invoice = VatInvoice.objects.get()
    assert (invoice.status, invoice.attempts) == (VatInvoiceStatus.PENDING, 1)

    for _ in range(invoicing.MAX_ATTEMPTS):
        invoicing.process()
    assert VatInvoice.objects.get().status == VatInvoiceStatus.FAILED


@pytest.mark.django_db
def test_email_failure_does_not_undo_an_issued_invoice(user, infakt, monkeypatch):
    invoicing.queue_from_stripe(stripe_invoice())
    invoicing.process()
    invoicing.process()
    infakt.down = True

    invoicing.process()

    invoice = VatInvoice.objects.get()
    assert invoice.status == VatInvoiceStatus.ISSUED
    assert invoice.emailed_at is None
    assert invoice.error.startswith("E-mail:")


@pytest.mark.django_db
def test_without_an_infakt_key_nothing_is_sent(user):
    invoicing.queue_from_stripe(stripe_invoice())

    assert invoicing.process() == 0
    assert VatInvoice.objects.get().status == VatInvoiceStatus.PENDING


@pytest.mark.django_db
def test_reconciliation_catches_missed_webhooks(user, infakt, fake_stripe):  # noqa: F811
    fake_stripe.v1.invoices.list.return_value.auto_paging_iter.return_value = [
        stripe.StripeObject.construct_from(stripe_invoice("in_missed"), "k")
    ]

    assert invoicing.reconcile() == 1
    assert invoicing.reconcile() == 0
    assert VatInvoice.objects.get().stripe_invoice_id == "in_missed"


# --- inFakt webhook ---------------------------------------------------------------


def _signed_post(client, data, secret=WEBHOOK_SECRET):
    body = json.dumps(data).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        reverse("billing:infakt-webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_INFAKT_SIGNATURE=signature,
    )


@pytest.mark.django_db
def test_infakt_webhook_needs_a_valid_signature(client, infakt):
    assert (
        _signed_post(client, {"verification_code": "x"}, secret="wrong").status_code
        == 401
    )
    response = client.post(
        reverse("billing:infakt-webhook"),
        data="{}",
        content_type="application/json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_infakt_webhook_activation_echoes_the_code(client, infakt):
    response = _signed_post(client, {"verification_code": "3e18cd8c"})

    assert response.json() == {"verification_code": "3e18cd8c"}


@pytest.mark.django_db
def test_infakt_webhook_finishes_the_job(client, user, infakt):
    invoicing.queue_from_stripe(stripe_invoice())
    invoicing.process()

    _signed_post(
        client,
        {
            "event": {"name": "async_invoice_creation_success", "uuid": "e1"},
            "resource": {
                "invoice_task_reference_number": "task-1",
                "processing_code": 201,
                "invoice_uuid": "uuid-1",
            },
        },
    )

    invoice = VatInvoice.objects.get()
    assert (invoice.status, invoice.number) == (VatInvoiceStatus.ISSUED, "7/09/2026")


# --- Panel ------------------------------------------------------------------------


@pytest.mark.django_db
def test_owner_sees_and_downloads_invoices(client, user, infakt):
    _customer(user)
    invoicing.queue_from_stripe(stripe_invoice())
    _run_until_done()
    invoice = VatInvoice.objects.get()
    client.force_login(user)

    html = page_text(client.get(reverse("billing:plan")))
    response = client.get(reverse("billing:invoice-pdf", args=[invoice.pk]))

    assert "Faktura 7/09/2026" in html
    assert "109,47 zł" in html
    assert response["Content-Type"] == "application/pdf"
    assert 'filename="Faktura-7-09-2026.pdf"' in response["Content-Disposition"]
    assert response.content == b"%PDF-1.4 faktura"


@pytest.mark.django_db
def test_nobody_else_can_download_an_invoice(client, user, infakt):
    _customer(user)
    invoicing.queue_from_stripe(stripe_invoice())
    _run_until_done()
    other = User.objects.create_user(email="other@example.com", password="x-pass-123!")
    client.force_login(other)

    response = client.get(
        reverse("billing:invoice-pdf", args=[VatInvoice.objects.get().pk])
    )

    assert response.status_code == 404


def test_nip_checksum():
    assert invoicing.valid_nip("5213017228")
    assert invoicing.valid_nip("9452121681")
    assert not invoicing.valid_nip("4434434434")
    assert not invoicing.valid_nip("123")


@pytest.mark.django_db
def test_wrong_nip_gives_a_private_invoice_and_tells_the_team(settings, user, infakt):
    invoice = invoicing.queue_from_stripe(
        stripe_invoice(
            name="Jan Kowalski", tax_ids=[{"type": "eu_vat", "value": "PL4434434434"}]
        )
    )
    invoicing.process()
    send_pending()

    assert invoice.client["client_business_activity_kind"] == "private_person"
    data = infakt.created_payload()["invoice"]
    assert "client_tax_code" not in data and "invalid_tax_id" not in data
    alert = mail.outbox[-1]
    assert alert.to == [settings.CONTACT_EMAIL]
    assert "4434434434" in alert.body
