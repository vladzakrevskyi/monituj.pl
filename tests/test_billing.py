import hashlib
import hmac
import json
import time
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import stripe
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import GuestAccess, User
from apps.audit.models import AuditEvent, AuditLog
from apps.billing import gateway, plans
from apps.billing.models import BillingAccount, StripeEvent
from apps.billing.notices import send_pending
from apps.billing.services import PlanLimitError, account_for, state_for
from apps.billing.tasks import send_trial_notices
from apps.clients.models import Client
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService
from apps.requests.models import Request, RequestItem, RequestItemStatus
from apps.requests.services import RequestService, in_progress
from tests.conftest import page_text

WEBHOOK_SECRET = "whsec_test"


def subscription(
    plan="biuro", interval="month", status="active", sub_id="sub_1", created=1, **extra
):
    return {
        "id": sub_id,
        "object": "subscription",
        "status": status,
        "created": created,
        "cancel_at": None,
        "cancel_at_period_end": False,
        "items": {
            "data": [
                {
                    "id": "si_1",
                    "current_period_end": 1_900_000_000,
                    "price": {
                        "lookup_key": f"monituj_{plan}_{interval}",
                        "metadata": {},
                    },
                }
            ]
        },
        **extra,
    }


def _listing(items):
    return SimpleNamespace(data=items, auto_paging_iter=lambda: iter(items))


class FakeStripe:
    """Stands in for stripe.StripeClient: records calls, answers like Stripe."""

    def __init__(self):
        self.v1 = MagicMock()
        self.subscriptions = []
        # Per customer when set, otherwise the same list for everyone.
        self.by_customer = {}
        self.v1.subscriptions.list.side_effect = lambda params: _listing(
            [
                stripe.StripeObject.construct_from(s, "k")
                for s in self.by_customer.get(
                    params.get("customer"), self.subscriptions
                )
            ]
        )
        # Customers found by email: none besides the stored one by default.
        self.customers = []
        self.v1.customers.list.side_effect = lambda params: _listing(
            [stripe.StripeObject.construct_from(c, "k") for c in self.customers]
        )
        self.v1.prices.list.return_value = SimpleNamespace(
            data=[
                SimpleNamespace(
                    lookup_key=plans.lookup_key(plan, interval),
                    id=f"price_{plan.code}_{interval}",
                )
                for plan in plans.PAID_PLANS
                for interval in plans.INTERVALS
            ]
        )
        # Real Stripe objects where the code reads nested fields: they are
        # not dicts, and the code must not treat them as such.
        self.v1.tax_rates.list.return_value.auto_paging_iter.return_value = [
            stripe.StripeObject.construct_from(
                {"id": "txr_vat23", "metadata": {"monituj_vat": "23"}}, "k"
            )
        ]
        configurations = self.v1.billing_portal.configurations.list.return_value
        configurations.auto_paging_iter.return_value = [
            stripe.StripeObject.construct_from(
                {"id": "bpc_1", "metadata": {"monituj": "1"}}, "k"
            )
        ]
        self.v1.customers.create.return_value = SimpleNamespace(id="cus_1")
        # No credit, payments, refunds or cards unless a test sets them.
        self.v1.customers.retrieve.return_value = stripe.StripeObject.construct_from(
            {"id": "cus_1", "balance": 0, "metadata": {}}, "k"
        )
        self.charges = []
        self.v1.charges.list.side_effect = lambda params: _listing(
            [stripe.StripeObject.construct_from(c, "k") for c in self.charges]
        )
        self.v1.refunds.list.return_value = _listing([])
        self.v1.customers.payment_methods.list.return_value = _listing([])
        self.v1.customers.tax_ids.list.return_value = SimpleNamespace(data=[])
        self.v1.checkout.sessions.create.return_value = SimpleNamespace(
            url="https://checkout.stripe.com/c/pay/cs_test_1"
        )
        self.v1.billing_portal.sessions.create.return_value = SimpleNamespace(
            url="https://billing.stripe.com/p/session/test_1"
        )


def gateway_cancel_params():
    return {"cancellation_details": {"comment": gateway.DELETION_COMMENT}}


@pytest.fixture
def invoice_details(user):
    from apps.billing.models import BillingProfile

    return BillingProfile.objects.create(
        user=user,
        kind="company",
        company_name="Biuro Rachunkowe Sp. z o.o.",
        tax_id="5213017228",
        street="ul. Prosta 1",
        post_code="00-001",
        city="Warszawa",
    )


@pytest.fixture
def fake_stripe(monkeypatch):
    fake = FakeStripe()
    monkeypatch.setattr(gateway, "client", lambda: fake)
    return fake


def _expire_trial(user):
    account = account_for(user)
    account.trial_ends_at = timezone.now() - timedelta(days=1)
    account.save()
    return account


def _subscribe(user, plan="start", interval="month", status="active"):
    account = account_for(user)
    account.stripe_mode = "sandbox"
    account.stripe_customer_id = "cus_1"
    account.stripe_subscription_id = "sub_1"
    account.plan = plan
    account.interval = interval
    account.status = status
    account.save()
    return account


def _open_requests(user, client_record, count):
    for number in range(count):
        request_obj = Request.objects.create(
            client=client_record, created_by=user, name=f"Prośba {number}"
        )
        RequestItem.objects.create(request=request_obj, name="Faktura")


def _signed(payload):
    timestamp = int(time.time())
    signature = hmac.new(
        WEBHOOK_SECRET.encode(), f"{timestamp}.{payload}".encode(), hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


def _event(event_type="customer.subscription.updated", customer="cus_1", **extra):
    return json.dumps(
        {
            "id": extra.pop("event_id", "evt_1"),
            "object": "event",
            "type": event_type,
            "livemode": extra.pop("livemode", False),
            "data": {"object": {"id": "sub_1", "customer": customer, **extra}},
        }
    )


def _post_webhook(client, payload, signature=None):
    return client.post(
        reverse("billing:webhook"),
        data=payload,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=signature or _signed(payload),
    )


# --- Plans -------------------------------------------------------------------


def test_prices_and_wording():
    assert plans.format_pln(3900) == "39 zł"
    assert plans.format_pln(plans.gross(3900)) == "47,97 zł"
    assert plans.format_pln(179000) == "1 790 zł"
    assert plans.requests_phrase(3) == "3 prośby"
    assert plans.requests_phrase(20) == "20 próśb"
    assert plans.requests_phrase(22) == "22 prośby"
    assert plans.requests_phrase(12) == "12 próśb"
    assert plans.from_lookup_key("monituj_pro_year") == (plans.PRO, plans.YEAR)
    assert plans.from_lookup_key("monituj_free_month") is None


def test_yearly_price_is_ten_months():
    for plan in plans.PAID_PLANS:
        assert plan.yearly == plan.monthly * 10


# --- Trial, Free and the limit ------------------------------------------------


@pytest.mark.django_db
def test_new_account_starts_a_30_day_trial_of_biuro(user):
    state = state_for(user)

    assert state.plan == plans.BIURO
    assert state.source == "trial"
    assert state.limit == 75
    assert state.trial_days_left == 30


@pytest.mark.django_db
def test_after_the_trial_the_account_is_free(user):
    _expire_trial(user)

    state = state_for(user)

    assert (state.plan, state.source, state.limit) == (plans.FREE, "free", 3)


@pytest.mark.django_db
def test_passwordless_accounts_are_on_free(user):
    GuestAccess.objects.create(user=user)

    assert state_for(user).source == "free"


@pytest.mark.django_db
def test_only_requests_still_waiting_count(user, client_record):
    _open_requests(user, client_record, 2)
    closed = Request.objects.create(
        client=client_record,
        created_by=user,
        name="Zamknięta",
        closed_at=timezone.now(),
    )
    RequestItem.objects.create(request=closed, name="Faktura")
    complete = Request.objects.create(
        client=client_record, created_by=user, name="Komplet"
    )
    RequestItem.objects.create(
        request=complete, name="Faktura", status=RequestItemStatus.ZAAKCEPTOWANY
    )
    unconfirmed = Request.objects.create(
        client=client_record,
        created_by=user,
        name="Bez konta",
        awaiting_confirmation=True,
    )
    RequestItem.objects.create(request=unconfirmed, name="Faktura")

    assert in_progress(user).count() == 2


@pytest.mark.django_db
def test_free_plan_refuses_the_fourth_request_in_progress(user, client_record):
    _expire_trial(user)
    _open_requests(user, client_record, 3)

    with pytest.raises(PlanLimitError, match="3 prośby w toku"):
        RequestService.create(
            owner=user,
            client_id=client_record.pk,
            name="Czwarta",
            description="",
            deadline=None,
            item_names=["Faktura"],
        )
    assert Request.objects.filter(created_by=user).count() == 3


@pytest.mark.django_db
def test_finished_request_frees_a_slot(user, client_record):
    _expire_trial(user)
    _open_requests(user, client_record, 3)
    RequestService.close(Request.objects.first(), actor=user)

    RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Nowa",
        description="",
        deadline=None,
        item_names=["Faktura"],
    )

    assert in_progress(user).count() == 3


@pytest.mark.django_db
def test_limit_message_shows_on_the_form_and_links_to_the_plan(
    client, user, client_record
):
    _expire_trial(user)
    _open_requests(user, client_record, 3)
    client.force_login(user)

    form = page_text(client.get(reverse("requests:create")))
    response = client.post(
        reverse("requests:create"),
        {"client": client_record.pk, "name": "Czwarta", "items": ["Faktura"]},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )

    assert "Masz już 3 z 3 próśb w toku" in form
    assert reverse("billing:plan") in form
    assert response.status_code == 400
    assert (
        "W planie Free możesz mieć jednocześnie 3 prośby w toku"
        in (response.json()["error"]["message"])
    )


@pytest.mark.django_db
def test_reopening_needs_a_free_slot(client, user, client_record):
    _expire_trial(user)
    _open_requests(user, client_record, 3)
    closed = Request.objects.create(
        client=client_record, created_by=user, name="Stara", closed_at=timezone.now()
    )
    RequestItem.objects.create(request=closed, name="Faktura")
    client.force_login(user)

    client.post(reverse("requests:close", args=[closed.pk]), {"action": "reopen"})

    closed.refresh_from_db()
    assert closed.closed_at is not None


@pytest.mark.django_db
def test_paid_plan_raises_the_limit(user, client_record):
    _expire_trial(user)
    _subscribe(user, plan="start")
    _open_requests(user, client_record, 3)

    RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Czwarta",
        description="",
        deadline=None,
        item_names=["Faktura"],
    )

    assert state_for(user).limit == 20


@pytest.mark.django_db
def test_a_subscription_from_the_other_stripe_mode_means_nothing(settings, user):
    _expire_trial(user)
    _subscribe(user, plan="pro")
    settings.STRIPE_MODE = "live"

    assert state_for(user).plan == plans.FREE


@pytest.mark.django_db
def test_past_due_keeps_the_plan_while_stripe_retries(user):
    _subscribe(user, plan="biuro", status="past_due")

    assert state_for(user).plan == plans.BIURO


# --- Checkout, portal and plan changes ----------------------------------------


@pytest.mark.django_db
def test_checkout_needs_the_early_start_request(
    client, user, fake_stripe, invoice_details
):
    client.force_login(user)

    response = client.post(
        reverse("billing:checkout"), {"plan": "start", "interval": "month"}
    )

    assert response.url == reverse("billing:plan")
    fake_stripe.v1.checkout.sessions.create.assert_not_called()


@pytest.mark.django_db
def test_checkout_sends_to_stripe_with_vat_and_records_the_request(
    client, user, fake_stripe, invoice_details
):
    client.force_login(user)

    response = client.post(
        reverse("billing:checkout"),
        {"plan": "biuro", "interval": "year", "early_start": "on"},
    )

    assert response.url == "https://checkout.stripe.com/c/pay/cs_test_1"
    params = fake_stripe.v1.checkout.sessions.create.call_args.kwargs["params"]
    assert params["customer"] == "cus_1"
    assert params["client_reference_id"] == str(user.pk)
    assert params["line_items"] == [{"price": "price_biuro_year", "quantity": 1}]
    assert params["subscription_data"]["default_tax_rates"] == ["txr_vat23"]
    # Invoice details come from Monituj, checked; Checkout asks only for a card.
    assert "tax_id_collection" not in params
    # Refunds are counted from list prices - no discount codes.
    assert "allow_promotion_codes" not in params
    update = fake_stripe.v1.customers.update.call_args
    assert update.args[0] == "cus_1"
    assert update.kwargs["params"]["name"] == "Biuro Rachunkowe Sp. z o.o."
    tax_id = fake_stripe.v1.customers.tax_ids.create.call_args
    assert tax_id.kwargs["params"] == {"type": "eu_vat", "value": "PL5213017228"}
    customer = fake_stripe.v1.customers.create.call_args.kwargs["params"]
    assert customer["metadata"] == {"user_id": str(user.pk)}
    account = account_for(user)
    assert (account.stripe_mode, account.stripe_customer_id) == ("sandbox", "cus_1")
    entry = AuditLog.objects.get(event=AuditEvent.CHECKOUT_STARTED)
    assert entry.metadata["early_start"] is True
    assert "14 dni" in entry.metadata["early_start_text"]


@pytest.mark.django_db
def test_no_vat_rate_when_vat_is_zero(
    client, settings, user, fake_stripe, invoice_details
):
    settings.BILLING_VAT_RATE = 0
    client.force_login(user)

    client.post(
        reverse("billing:checkout"),
        {"plan": "start", "interval": "month", "early_start": "on"},
    )

    params = fake_stripe.v1.checkout.sessions.create.call_args.kwargs["params"]
    assert "default_tax_rates" not in params["subscription_data"]


@pytest.mark.django_db
def test_subscribed_account_changes_plan_instead_of_paying_twice(
    client, user, fake_stripe, invoice_details
):
    _subscribe(user, plan="start")
    fake_stripe.v1.subscriptions.retrieve.return_value = (
        stripe.StripeObject.construct_from(subscription(plan="start"), "k")
    )
    client.force_login(user)

    response = client.post(
        reverse("billing:checkout"),
        {"plan": "pro", "interval": "month", "early_start": "on"},
    )

    assert response.url == "https://billing.stripe.com/p/session/test_1"
    fake_stripe.v1.checkout.sessions.create.assert_not_called()
    params = fake_stripe.v1.billing_portal.sessions.create.call_args.kwargs["params"]
    flow = params["flow_data"]["subscription_update_confirm"]
    assert flow["items"] == [{"id": "si_1", "price": "price_pro_month", "quantity": 1}]
    assert params["configuration"] == "bpc_1"


@pytest.mark.django_db
def test_passwordless_account_must_set_a_password_first(client, user, fake_stripe):
    GuestAccess.objects.create(user=user)
    client.force_login(user)

    response = client.post(
        reverse("billing:checkout"),
        {"plan": "start", "interval": "month", "early_start": "on"},
    )

    assert response.url == reverse("billing:plan")
    fake_stripe.v1.checkout.sessions.create.assert_not_called()


@pytest.mark.django_db
def test_stripe_outage_shows_a_message_not_an_error(
    client, user, fake_stripe, invoice_details
):
    fake_stripe.v1.checkout.sessions.create.side_effect = stripe.APIConnectionError(
        "down"
    )
    client.force_login(user)

    response = client.post(
        reverse("billing:checkout"),
        {"plan": "start", "interval": "month", "early_start": "on"},
        follow=True,
    )

    assert "Płatności są chwilowo niedostępne" in page_text(response)


@pytest.mark.django_db
def test_return_from_checkout_activates_the_plan_at_once(client, user, fake_stripe):
    account = account_for(user)
    account.stripe_mode, account.stripe_customer_id = "sandbox", "cus_1"
    account.save()
    fake_stripe.v1.checkout.sessions.retrieve.return_value = SimpleNamespace(
        client_reference_id=str(user.pk), customer="cus_1"
    )
    fake_stripe.subscriptions = [subscription(plan="pro", interval="year")]
    client.force_login(user)

    response = client.get(
        reverse("billing:return") + "?session_id=cs_test_a1B2c3D4e5F6g7", follow=True
    )

    state = state_for(user)
    assert (state.plan, state.source) == (plans.PRO, "subscription")
    assert "Plan Pro jest aktywny" in page_text(response)


@pytest.mark.django_db
def test_someone_elses_checkout_session_changes_nothing(client, user, fake_stripe):
    fake_stripe.v1.checkout.sessions.retrieve.return_value = SimpleNamespace(
        client_reference_id="999", customer="cus_other"
    )
    fake_stripe.subscriptions = [subscription(plan="pro")]
    client.force_login(user)

    client.get(reverse("billing:return") + "?session_id=cs_test_other")

    assert state_for(user).source == "trial"
    fake_stripe.v1.subscriptions.list.assert_not_called()


# --- Webhooks ------------------------------------------------------------------


@pytest.mark.django_db
def test_webhook_syncs_the_subscription_from_stripe(client, user, fake_stripe):
    account = account_for(user)
    account.stripe_mode, account.stripe_customer_id = "sandbox", "cus_1"
    account.save()
    fake_stripe.subscriptions = [
        subscription(plan="start", status="canceled", sub_id="sub_old", created=1),
        subscription(plan="biuro", interval="year", created=2, cancel_at=1_900_000_000),
    ]

    response = _post_webhook(client, _event())

    assert response.status_code == 200
    account.refresh_from_db()
    assert (account.plan, account.interval, account.status) == (
        "biuro",
        "year",
        "active",
    )
    assert account.cancel_at is not None
    assert AuditLog.objects.filter(event=AuditEvent.PLAN_CHANGED).count() == 1


@pytest.mark.django_db
def test_webhook_rejects_a_forged_signature(client, user, fake_stripe):
    payload = _event()

    response = _post_webhook(client, payload, signature="t=1,v1=deadbeef")

    assert response.status_code == 400
    assert not StripeEvent.objects.exists()


@pytest.mark.django_db
def test_webhook_handles_each_event_once(client, user, fake_stripe):
    account = account_for(user)
    account.stripe_mode, account.stripe_customer_id = "sandbox", "cus_1"
    account.save()
    fake_stripe.subscriptions = [subscription()]
    payload = _event()

    _post_webhook(client, payload)
    _post_webhook(client, payload)

    assert fake_stripe.v1.subscriptions.list.call_count == 1


@pytest.mark.django_db
def test_live_events_are_ignored_in_sandbox_mode(client, user, fake_stripe):
    account = account_for(user)
    account.stripe_mode, account.stripe_customer_id = "sandbox", "cus_1"
    account.save()

    _post_webhook(client, _event(livemode=True))

    fake_stripe.v1.subscriptions.list.assert_not_called()


@pytest.mark.django_db
def test_cancelled_subscription_returns_the_account_to_free(client, user, fake_stripe):
    _expire_trial(user)
    _subscribe(user, plan="pro")
    fake_stripe.subscriptions = [subscription(plan="pro", status="canceled")]

    _post_webhook(client, _event("customer.subscription.deleted"))

    assert state_for(user).plan == plans.FREE


@pytest.mark.django_db
def test_stripe_failure_asks_for_a_retry(client, user, fake_stripe):
    _subscribe(user)
    fake_stripe.v1.subscriptions.list.side_effect = stripe.APIConnectionError("down")

    response = _post_webhook(client, _event())

    assert response.status_code == 503
    # Not marked as handled, so Stripe's retry is processed.
    assert not StripeEvent.objects.exists()


# --- Pages ----------------------------------------------------------------------


@pytest.mark.django_db
def test_plan_page_shows_usage_trial_and_test_card(
    client, user, client_record, invoice_details
):
    _open_requests(user, client_record, 2)
    client.force_login(user)

    html = page_text(client.get(reverse("billing:plan")))

    assert "Okres próbny" in html
    assert "zostało 30 dni" in html
    assert "<strong>2</strong> z 75" in html
    assert "4242 4242 4242 4242" in html
    assert 'name="early_start"' in html
    assert "39 zł" in html and "47,97 zł z VAT" in html
    assert "Plan Biuro" in html  # sidebar meter


@pytest.mark.django_db
def test_plan_page_for_a_subscriber(client, user):
    account = _subscribe(user, plan="biuro", interval="year")
    account.current_period_end = timezone.now() + timedelta(days=100)
    account.save()
    client.force_login(user)

    html = page_text(client.get(reverse("billing:plan")))

    assert "890 zł netto rocznie" in html
    assert "Karta i subskrypcja" in html
    assert 'name="early_start"' not in html
    assert reverse("billing:change") in html


@pytest.mark.django_db
def test_public_pricing_lists_every_plan(client):
    html = page_text(client.get(reverse("pages:pricing")))

    for text in ("Free", "Start", "Biuro", "Pro", "39 zł", "89 zł", "179 zł"):
        assert text in html
    assert "30 dni za darmo" in html
    assert '"lowPrice": "0.00"' in html
    assert "obecnie bezpłatnie" not in html.lower()


@pytest.mark.django_db
def test_terms_describe_payments_and_withdrawal(client):
    html = page_text(client.get(reverse("legal:terms")))

    assert 'id="platnosci"' in html
    assert "Stripe Payments Europe" in html
    assert "23%" in html
    assert "proporcjonalnie do ich zakresu" in html


# --- Emails ------------------------------------------------------------------------


@pytest.mark.django_db
def test_emails_to_recipients_carry_no_advertising(user, request_record, request_item):
    # Recipients never agreed to marketing - a free plan changes nothing.
    _expire_trial(user)

    EmailService.send(
        EmailTemplate.INVITATION, to_email="acme@example.com", request=request_record
    )

    invitation = mail.outbox[0]
    assert "zacznij za darmo" not in invitation.body
    assert "zacznij za darmo" not in invitation.alternatives[0][0]


@pytest.mark.django_db
def test_trial_reminders_go_out_once_each(user):
    user.email_verified_at = timezone.now()
    user.save()
    account = account_for(user)
    now = timezone.now()

    account.trial_ends_at = now + timedelta(days=6)
    account.save()
    assert send_trial_notices(now) == 1
    assert send_trial_notices(now) == 0
    assert "Za 7 dni" in mail.outbox[0].subject

    assert send_trial_notices(now + timedelta(days=5, hours=12)) == 1
    assert "Jutro" in mail.outbox[1].subject

    assert send_trial_notices(now + timedelta(days=6, hours=1)) == 1
    assert "zakończony" in mail.outbox[2].subject
    assert send_trial_notices(now + timedelta(days=7)) == 0


@pytest.mark.django_db
def test_no_trial_reminders_for_subscribers_or_old_accounts(user):
    user.email_verified_at = timezone.now()
    user.save()
    account = _subscribe(user)
    account.trial_ends_at = timezone.now() + timedelta(days=1)
    account.save()
    other = User.objects.create_user(email="old@example.com", password="x-pass-123!")
    other.email_verified_at = timezone.now()
    other.save()
    old = account_for(other)
    old.trial_ends_at = timezone.now() - timedelta(days=60)
    old.save()

    assert send_trial_notices() == 0


# --- Account deletion ----------------------------------------------------------------


@pytest.mark.django_db
def test_deleting_the_account_cancels_the_subscription(client, user, fake_stripe):
    from apps.accounts.services import AccountDeletionService

    _subscribe(user)
    fake_stripe.subscriptions = [subscription()]
    client.force_login(user)
    AccountDeletionService.request_deletion(user, "s3cr3t-pass!")
    token = (
        mail.outbox[-1].body.split("/ustawienia/usun-konto/potwierdz/")[1].split("/")[0]
    )

    client.post(reverse("accounts:account-deletion-confirm", args=[token]))

    fake_stripe.v1.subscriptions.cancel.assert_called_once_with(
        "sub_1", params=gateway_cancel_params()
    )
    assert not User.objects.filter(pk=user.pk).exists()
    assert not BillingAccount.objects.exists()


@pytest.mark.django_db
def test_account_stays_when_stripe_cannot_cancel(client, user, fake_stripe):
    from apps.accounts.services import AccountDeletionService

    _subscribe(user)
    fake_stripe.subscriptions = [subscription()]
    fake_stripe.v1.subscriptions.cancel.side_effect = stripe.APIConnectionError("down")
    AccountDeletionService.request_deletion(user, "s3cr3t-pass!")
    token = (
        mail.outbox[-1].body.split("/ustawienia/usun-konto/potwierdz/")[1].split("/")[0]
    )

    response = client.post(reverse("accounts:account-deletion-confirm", args=[token]))

    assert User.objects.filter(pk=user.pk).exists()
    assert "Nie udało się anulować subskrypcji" in page_text(response)


@pytest.mark.django_db
def test_demo_accounts_have_no_limit(client_record):
    from apps.demo.models import DemoAccount

    demo_user = User.objects.create_user(email="demo@demo.monituj.pl")
    DemoAccount.objects.create(
        user=demo_user, ip_hash="x", expires_at=timezone.now() + timedelta(hours=1)
    )
    _expire_trial(demo_user)
    demo_client = Client.objects.create(
        owner=demo_user, name="Demo", email="demo-client@example.com"
    )
    _open_requests(demo_user, demo_client, 5)

    assert state_for(demo_user).limit is None


@pytest.mark.django_db
def test_downgrade_below_current_usage_is_explained(client, user, client_record):
    _subscribe(user, plan="biuro")
    _open_requests(user, client_record, 21)
    client.force_login(user)

    html = page_text(client.get(reverse("billing:plan")))

    assert html.count("Masz 21 próśb w toku. Po zmianie nic się nie zatrzyma") == 1
    assert "mniej niż 20" in html


# --- Emails about subscription changes ------------------------------------------


def _snap(plan="biuro", interval="month", status="active", cancel_at=None):
    from apps.billing.notices import Snapshot

    return Snapshot(plan, interval, status, cancel_at, "sandbox")


@pytest.mark.parametrize(
    ("before", "after", "kind"),
    [
        (_snap(plan="free", status=""), _snap(), "started"),
        (_snap(plan="start"), _snap(plan="pro"), "upgraded"),
        (_snap(plan="pro"), _snap(plan="start"), "downgraded"),
        (_snap(), _snap(interval="year"), "interval"),
        (_snap(), _snap(cancel_at=timezone.now()), "cancel_scheduled"),
        (_snap(cancel_at=timezone.now()), _snap(), "resumed"),
        (_snap(), _snap(status="canceled"), "ended"),
        (_snap(), _snap(status="past_due"), "payment_failed"),
        (_snap(status="past_due"), _snap(), None),
        (_snap(plan="free", status=""), _snap(status="incomplete"), None),
        (_snap(), _snap(), None),
    ],
)
def test_change_kinds(before, after, kind):
    from apps.billing.notices import change_kind

    assert change_kind(before, after) == kind


def _customer(user):
    account = account_for(user)
    account.stripe_mode, account.stripe_customer_id = "sandbox", "cus_1"
    account.save()
    return account


@pytest.mark.django_db
def test_each_change_is_mailed_once(
    client, user, fake_stripe, django_capture_on_commit_callbacks
):
    _customer(user)
    fake_stripe.subscriptions = [subscription(plan="biuro")]

    with django_capture_on_commit_callbacks(execute=True):
        _post_webhook(client, _event(event_id="evt_1"))
        _post_webhook(client, _event(event_id="evt_2"))
        client.get(reverse("billing:plan") + "?zmiana=1")
    send_pending()

    assert [m.subject for m in mail.outbox] == ["Plan Biuro jest aktywny – Monituj"]
    body = mail.outbox[0].body.replace("\u00a0", " ")
    assert "75 próśb w toku" in body
    assert "89 zł netto (109,47 zł z VAT) miesięcznie" in body.replace(" ", " ")


@pytest.mark.django_db
def test_cancelling_mails_the_end_date_and_shows_it_in_the_panel(
    client, user, fake_stripe, django_capture_on_commit_callbacks
):
    _expire_trial(user)
    _subscribe(user, plan="biuro")
    ends = 1_900_000_000
    fake_stripe.subscriptions = [subscription(plan="biuro", cancel_at=ends)]
    client.force_login(user)

    with django_capture_on_commit_callbacks(execute=True):
        # Back from the portal: the page syncs without waiting for a webhook.
        html = page_text(client.get(reverse("billing:plan") + "?zmiana=1"))
    send_pending()

    assert mail.outbox[0].subject.startswith("Subskrypcja anulowana – plan Biuro")
    assert "nie będą pobierane" in mail.outbox[0].body.replace("\u00a0", " ")
    assert "Anulowany – do" in html
    assert "kolejne płatności nie będą pobierane" in html
    assert "Wznów subskrypcję" in html
    assert "Następna płatność" not in html


@pytest.mark.django_db
def test_plan_changes_and_the_end_are_mailed(
    client, user, fake_stripe, django_capture_on_commit_callbacks
):
    _expire_trial(user)
    _subscribe(user, plan="biuro")
    _open_requests(
        user, Client.objects.create(owner=user, name="K", email="k@example.com"), 5
    )

    with django_capture_on_commit_callbacks(execute=True):
        fake_stripe.subscriptions = [subscription(plan="start")]
        gateway.refresh(account_for(user))
        fake_stripe.subscriptions = [subscription(plan="start", interval="year")]
        gateway.refresh(account_for(user))
        fake_stripe.subscriptions = [
            subscription(plan="start", interval="year", status="past_due")
        ]
        gateway.refresh(account_for(user))
        fake_stripe.subscriptions = [
            subscription(plan="start", interval="year", status="canceled")
        ]
        gateway.refresh(account_for(user))

    send_pending()
    subjects = [m.subject for m in mail.outbox]
    assert subjects == [
        "Zmieniłeś plan na Start – Monituj",
        "Płacisz teraz rocznie – Monituj",
        "Nie udało się pobrać płatności za plan Start – Monituj",
        "Plan Start się zakończył – działasz w planie Free",
    ]
    assert "Masz więcej próśb w toku" in mail.outbox[3].body.replace("\u00a0", " ")


# --- Security fixes -------------------------------------------------------------


@pytest.mark.django_db
def test_checkout_reuses_a_customer_already_made_for_the_user(
    client, user, fake_stripe, invoice_details
):
    fake_stripe.customers = [{"id": "cus_old", "metadata": {"user_id": str(user.pk)}}]
    client.force_login(user)

    client.post(
        reverse("billing:checkout"),
        {"plan": "start", "interval": "month", "early_start": "on"},
    )

    fake_stripe.v1.customers.create.assert_not_called()
    params = fake_stripe.v1.checkout.sessions.create.call_args.kwargs["params"]
    assert params["customer"] == "cus_old"


@pytest.mark.django_db
def test_payment_on_an_unknown_customer_of_the_user_is_honored(
    client, user, fake_stripe
):
    # Stored customer pays for nothing; the payment went to another one.
    _customer(user)
    fake_stripe.by_customer = {
        "cus_1": [],
        "cus_2": [subscription(plan="pro", sub_id="sub_2")],
    }
    fake_stripe.v1.customers.retrieve.return_value = stripe.StripeObject.construct_from(
        {"id": "cus_2", "metadata": {"user_id": str(user.pk)}}, "k"
    )

    _post_webhook(client, _event(customer="cus_2"))

    account = account_for(user)
    assert account.stripe_customer_id == "cus_2"
    assert state_for(user).plan == plans.PRO


@pytest.mark.django_db
def test_second_paying_customer_alerts_the_team(settings, client, user, fake_stripe):
    _customer(user)
    fake_stripe.by_customer = {
        "cus_1": [subscription(plan="biuro")],
        "cus_2": [subscription(plan="pro", sub_id="sub_2")],
    }
    fake_stripe.v1.customers.retrieve.return_value = stripe.StripeObject.construct_from(
        {"id": "cus_2", "metadata": {"user_id": str(user.pk)}}, "k"
    )

    _post_webhook(client, _event(customer="cus_2"))
    send_pending()

    assert account_for(user).stripe_customer_id == "cus_1"
    alert = mail.outbox[-1]
    assert alert.to == [settings.CONTACT_EMAIL]
    assert "drugiego klienta Stripe" in alert.subject


@pytest.mark.django_db
def test_double_subscription_alerts_once(settings, user, fake_stripe):
    _customer(user)
    fake_stripe.subscriptions = [
        subscription(plan="biuro", sub_id="sub_a", created=1),
        subscription(plan="start", sub_id="sub_b", created=2),
    ]

    gateway.refresh(account_for(user))
    gateway.refresh(account_for(user))
    send_pending()

    alerts = [m for m in mail.outbox if m.to == [settings.CONTACT_EMAIL]]
    assert len(alerts) == 1
    assert "sub_a, sub_b" in alerts[0].body


@pytest.mark.django_db
def test_deletion_cancels_subscriptions_monituj_never_stored(client, user, fake_stripe):
    from apps.accounts.services import AccountDeletionService

    # Only the customer id stored - the subscription never arrived locally.
    _customer(user)
    fake_stripe.customers = [{"id": "cus_9", "metadata": {"user_id": str(user.pk)}}]
    fake_stripe.by_customer = {
        "cus_9": [subscription(sub_id="sub_live", status="active")]
    }
    AccountDeletionService.request_deletion(user, "s3cr3t-pass!")
    token = mail.outbox[-1].body.split("/ustawienia/usun-konto/potwierdz/")[1]
    token = token.split("/")[0]

    client.post(reverse("accounts:account-deletion-confirm", args=[token]))

    fake_stripe.v1.subscriptions.cancel.assert_called_once_with(
        "sub_live", params=gateway_cancel_params()
    )
    assert not User.objects.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_stripe_reads_from_links_are_limited(client, user, fake_stripe):
    _customer(user)
    client.force_login(user)

    for _ in range(35):
        client.get(reverse("billing:plan") + "?zmiana=1")
    client.get(reverse("billing:return") + "?session_id=cs_test_a1B2c3D4e5F6g7")
    client.get(reverse("billing:return") + "?session_id=cs_x")

    assert fake_stripe.v1.subscriptions.list.call_count == 30
    fake_stripe.v1.checkout.sessions.retrieve.assert_not_called()


@pytest.mark.django_db
def test_refunds_and_disputes_alert_the_team(settings, client, user, fake_stripe):
    _customer(user)
    fake_stripe.subscriptions = [subscription()]
    fake_stripe.v1.charges.retrieve.return_value = SimpleNamespace(customer="cus_1")

    _post_webhook(
        client,
        _event(
            "charge.refunded",
            event_id="evt_r",
            amount_refunded=10947,
            payment_intent="pi_1",
        ),
    )
    dispute = json.loads(_event("charge.dispute.created", event_id="evt_d"))
    dispute["data"]["object"] = {"id": "dp_1", "charge": "ch_1", "amount": 10947}
    _post_webhook(client, json.dumps(dispute))
    send_pending()

    subjects = [m.subject for m in mail.outbox if m.to == [settings.CONTACT_EMAIL]]
    assert subjects == [
        "[Monituj – płatności] Zwrot płatności w Stripe",
        "[Monituj – płatności] Klient zakwestionował płatność (spór)",
    ]
    body = mail.outbox[-1].body.replace("\u00a0", " ")
    assert user.email in body and "109,47 zł" in body


@pytest.mark.django_db
def test_unpaid_plan_lasts_only_the_grace_period(user):
    _expire_trial(user)
    account = _subscribe(user, plan="pro", status="past_due")
    account.past_due_since = timezone.now() - timedelta(days=13)
    account.save()
    assert state_for(user).plan == plans.PRO

    account.past_due_since = timezone.now() - timedelta(days=15)
    account.save()
    assert state_for(user).plan == plans.FREE


@pytest.mark.django_db
def test_past_due_start_is_recorded_and_cleared(user, fake_stripe):
    _customer(user)
    fake_stripe.subscriptions = [subscription(status="past_due")]
    gateway.refresh(account_for(user))
    assert account_for(user).past_due_since is not None

    fake_stripe.subscriptions = [subscription(status="active")]
    gateway.refresh(account_for(user))
    assert account_for(user).past_due_since is None


@pytest.mark.django_db
def test_early_start_request_outlives_the_account(
    client, user, fake_stripe, invoice_details
):
    from apps.accounts.erasure import erase_account
    from apps.billing.models import CheckoutConsent

    client.force_login(user)
    client.post(
        reverse("billing:checkout"),
        {"plan": "biuro", "interval": "month", "early_start": "on"},
        HTTP_USER_AGENT="TestBrowser",
    )
    erase_account(user)

    consent = CheckoutConsent.objects.get()
    assert consent.user is None
    assert consent.email == "owner@example.com"
    assert consent.stripe_customer_id == "cus_1"
    assert "14 dni" in consent.text
    assert consent.user_agent == "TestBrowser"


@pytest.mark.django_db
def test_admin_finds_accounts_over_their_limit(user, client_record):
    from apps.billing.admin import over_limit_ids

    _expire_trial(user)
    _open_requests(user, client_record, 5)

    assert over_limit_ids() == [account_for(user).pk]
