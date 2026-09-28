# ruff: noqa: F811 - fixtures imported from test_billing are redefined as arguments
"""Money back (Regulamin § 5a): a deleted account gets the unused part of
its payment and any downgrade credit back, and its Stripe customer is
stripped of personal data; credit left when a subscription ends goes back
too."""

import json
import time

import pytest
import stripe
from django.core import mail
from django.urls import reverse

from apps.accounts.models import User
from apps.billing import gateway
from apps.billing.models import VatInvoice
from apps.billing.notices import send_pending
from tests.test_billing import (  # noqa: F401 - fake_stripe is a fixture
    _customer,
    _event,
    _listing,
    _post_webhook,
    _subscribe,
    fake_stripe,
    subscription,
)

DAY = 86_400


def _current(plan="biuro", status="active", days_used=10, days_left=20, **extra):
    now = int(time.time())
    data = subscription(plan=plan, status=status, **extra)
    data["items"]["data"][0]["current_period_start"] = now - days_used * DAY
    data["items"]["data"][0]["current_period_end"] = now + days_left * DAY
    return data


def _delete(client, user):
    from apps.accounts.services import AccountDeletionService

    AccountDeletionService.request_deletion(user, "s3cr3t-pass!")
    token = mail.outbox[-1].body.split("/ustawienia/usun-konto/potwierdz/")[1]
    return client.post(
        reverse("accounts:account-deletion-confirm", args=[token.split("/")[0]])
    )


def _refunded(fake):
    return [
        (call.kwargs["params"]["charge"], call.kwargs["params"]["amount"])
        for call in fake.v1.refunds.create.call_args_list
    ]


def test_unused_value_is_the_share_of_the_period_left():
    now = int(time.time())
    # Biuro: 89 zł net = 109,47 zł gross; two thirds of the period left.
    assert gateway.unused_value(_current(), now) == 7298
    assert gateway.unused_value(_current(days_left=0, days_used=30), now) == 0
    # A period not paid for gives nothing back.
    assert gateway.unused_value(_current(status="past_due"), now) == 0


@pytest.mark.django_db
def test_deletion_refunds_the_time_left_and_the_credit(
    settings, client, user, fake_stripe
):
    _subscribe(user, plan="biuro")
    VatInvoice.objects.create(
        user=user,
        email=user.email,
        stripe_mode="sandbox",
        stripe_invoice_id="in_1",
        description="Plan Biuro",
        gross=10947,
        paid_at="2026-09-01T10:00Z",
        number="FV 7/09/2026",
        status="issued",
    )
    fake_stripe.subscriptions = [_current()]
    fake_stripe.v1.customers.retrieve.return_value = stripe.StripeObject.construct_from(
        {"id": "cus_1", "balance": -1000, "metadata": {"user_id": str(user.pk)}}, "k"
    )
    fake_stripe.charges = [
        {
            "id": "ch_new",
            "paid": True,
            "status": "succeeded",
            "amount_captured": 5000,
            "amount_refunded": 0,
        },
        {
            "id": "ch_old",
            "paid": True,
            "status": "succeeded",
            "amount_captured": 10947,
            "amount_refunded": 0,
        },
    ]

    _delete(client, user)
    send_pending()

    assert not User.objects.filter(pk=user.pk).exists()
    # 72,98 zł for the 20 days left + 10 zł credit, newest payment first.
    assert _refunded(fake_stripe) == [("ch_new", 5000), ("ch_old", 3298)]
    refund = fake_stripe.v1.refunds.create.call_args.kwargs["params"]
    assert refund["metadata"] == {"monituj_reason": "account_deleted"}
    # The refunded credit is cleared.
    balance = fake_stripe.v1.customers.balance_transactions.create.call_args
    assert balance.args[0] == "cus_1" and balance.kwargs["params"]["amount"] == 1000
    # Personal data is removed from the Stripe customer.
    update = fake_stripe.v1.customers.update.call_args
    assert update.args[0] == "cus_1"
    assert update.kwargs["params"]["email"] == ""
    assert update.kwargs["params"]["name"] == ""
    assert update.kwargs["params"]["metadata"]["user_id"] == ""
    # The owner is told, the team issues the correction.
    goodbye = [m for m in mail.outbox if m.to == [user.email]][-1]
    assert "82,98" in goodbye.body.replace(" ", " ")
    alert = next(m for m in mail.outbox if m.to == [settings.CONTACT_EMAIL])
    assert "korygującą do faktury FV 7/09/2026" in alert.body.replace("\u00a0", " ")


@pytest.mark.django_db
def test_a_failed_refund_does_not_block_the_deletion(
    settings, client, user, fake_stripe
):
    _subscribe(user, plan="biuro")
    fake_stripe.subscriptions = [_current()]
    fake_stripe.charges = [
        {
            "id": "ch_1",
            "paid": True,
            "status": "succeeded",
            "amount_captured": 10947,
            "amount_refunded": 0,
        }
    ]
    fake_stripe.v1.refunds.create.side_effect = stripe.APIConnectionError("down")

    _delete(client, user)
    send_pending()

    assert not User.objects.filter(pk=user.pk).exists()
    alert = next(m for m in mail.outbox if m.to == [settings.CONTACT_EMAIL])
    assert "się nie udał" in alert.body


@pytest.mark.django_db
def test_credit_left_after_the_subscription_ends_goes_back(
    settings, client, user, fake_stripe
):
    _customer(user)
    fake_stripe.subscriptions = [subscription(status="canceled")]
    fake_stripe.v1.customers.retrieve.return_value = stripe.StripeObject.construct_from(
        {"id": "cus_1", "balance": -2500, "metadata": {}}, "k"
    )
    fake_stripe.charges = [
        {
            "id": "ch_1",
            "paid": True,
            "status": "succeeded",
            "amount_captured": 10947,
            "amount_refunded": 0,
        }
    ]

    _post_webhook(client, _event("customer.subscription.deleted", status="canceled"))
    send_pending()

    assert _refunded(fake_stripe) == [("ch_1", 2500)]
    alert = next(m for m in mail.outbox if m.to == [settings.CONTACT_EMAIL])
    assert "zwrot niewykorzystanego salda" in alert.subject


@pytest.mark.django_db
def test_no_second_refund_for_a_subscription_ended_by_deletion(
    client, user, fake_stripe
):
    _customer(user)
    fake_stripe.subscriptions = [subscription(status="canceled")]
    fake_stripe.v1.customers.retrieve.return_value = stripe.StripeObject.construct_from(
        {"id": "cus_1", "balance": -2500, "metadata": {}}, "k"
    )

    _post_webhook(
        client,
        _event(
            "customer.subscription.deleted",
            status="canceled",
            cancellation_details={"comment": gateway.DELETION_COMMENT},
        ),
    )

    fake_stripe.v1.refunds.create.assert_not_called()


@pytest.mark.django_db
def test_refunds_made_by_monituj_do_not_alert_twice(
    settings, client, user, fake_stripe
):
    _customer(user)
    fake_stripe.v1.refunds.list.return_value = _listing(
        [
            stripe.StripeObject.construct_from(
                {"id": "re_1", "metadata": {"monituj_reason": "account_deleted"}}, "k"
            )
        ]
    )
    payload = json.loads(_event("charge.refunded", event_id="evt_r"))
    payload["data"]["object"] = {"id": "ch_1", "customer": "cus_1"}

    _post_webhook(client, json.dumps(payload))
    send_pending()

    assert not [m for m in mail.outbox if m.to == [settings.CONTACT_EMAIL]]
