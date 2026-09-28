# ruff: noqa: F811 - fixtures imported from test_billing are redefined as arguments
"""What a buyer - a consumer in particular - is told and given: the order
button says it costs money, prices show net or gross, the "plan started"
email confirms the contract with the Regulamin attached, and the withdrawal
form is on the site."""

import pytest
from django.core import mail
from django.urls import reverse

from apps.billing.models import BillingProfile, CheckoutConsent
from apps.billing.notices import send_pending
from tests.conftest import page_text
from tests.test_billing import (  # noqa: F401 - fake_stripe is a fixture
    _customer,
    _event,
    _expire_trial,
    _post_webhook,
    _subscribe,
    fake_stripe,
    invoice_details,
    subscription,
)


def _text(value):
    return value.replace(" ", " ")


@pytest.mark.django_db
def test_the_first_order_button_says_it_costs_money(client, user, invoice_details):
    client.force_login(user)

    html = page_text(client.get(reverse("billing:plan")))

    assert html.count("Zamawiam i płacę") == 6  # 3 paid plans x 2 intervals
    assert "odnawia się automatycznie" in html
    assert reverse("legal:withdrawal") in html


@pytest.mark.django_db
def test_changes_that_charge_now_say_so(client, user):
    _subscribe(user, plan="biuro", interval="month")
    client.force_login(user)

    html = page_text(client.get(reverse("billing:plan")))

    # Pro (dearer) and every yearly option charge at once; Start monthly doesn't.
    assert html.count("Zmieniam i dopłacam") == 4
    assert "Zmień na Start" in html


@pytest.mark.django_db
def test_prices_switch_between_net_and_gross(client):
    html = _text(page_text(client.get(reverse("pages:pricing"))))

    assert 'name="vat" value="net"' in html and 'name="vat" value="gross"' in html
    assert 'data-vat="gross"><strong>47,97 zł</strong><span>brutto / mies.' in html
    assert 'data-vat="net"><strong>39 zł</strong><span>netto / mies.' in html


@pytest.mark.django_db
def test_net_prices_are_the_default_for_everyone(client, user):
    BillingProfile.objects.create(
        user=user,
        kind="person",
        first_name="Jan",
        last_name="Kowalski",
        street="ul. Prosta 1",
        post_code="00-001",
        city="Warszawa",
    )
    client.force_login(user)

    html = page_text(client.get(reverse("billing:plan")))

    assert 'name="vat" value="net" form="price-switches-none" checked' in html
    assert 'value="gross" form="price-switches-none" checked' not in html


@pytest.mark.django_db
def test_plan_started_email_confirms_the_contract(
    client, user, fake_stripe, django_capture_on_commit_callbacks
):
    CheckoutConsent.objects.create(
        user=user,
        email=user.email,
        stripe_mode="sandbox",
        plan="biuro",
        interval="month",
        text="Żądam rozpoczęcia świadczenia usługi…",
    )
    _customer(user)
    fake_stripe.subscriptions = [subscription(plan="biuro")]

    with django_capture_on_commit_callbacks(execute=True):
        _post_webhook(client, _event(event_id="evt_1"))
    send_pending()

    message = mail.outbox[0]
    body = _text(message.body)
    assert "POTWIERDZENIE UMOWY" in body
    assert "usługę świadczymy od razu" in body
    assert "możesz odstąpić od niej bez podawania przyczyny do" in body
    assert reverse("legal:withdrawal") in body
    [(filename, content, mimetype)] = message.attachments
    assert filename == "Monituj-regulamin.html" and mimetype == "text/html"
    document = content.decode() if isinstance(content, bytes) else content
    for title in (
        "Regulamin serwisu Monituj",
        "Umowa powierzenia przetwarzania danych osobowych",
        "Wzór formularza odstąpienia od umowy",
    ):
        assert title in document
    # Links inside the saved file still lead to the site.
    assert '<base href="http://localhost:8000/">' in document


@pytest.mark.django_db
def test_later_changes_carry_no_attachment(
    client, user, fake_stripe, django_capture_on_commit_callbacks
):
    _expire_trial(user)
    _subscribe(user, plan="biuro")
    fake_stripe.subscriptions = [subscription(plan="pro")]

    with django_capture_on_commit_callbacks(execute=True):
        _post_webhook(client, _event(event_id="evt_1"))
    send_pending()

    assert mail.outbox and not mail.outbox[0].attachments


@pytest.mark.django_db
def test_withdrawal_page_has_the_model_form(client):
    html = page_text(client.get(reverse("legal:withdrawal")))

    assert "Wzór formularza odstąpienia od umowy" in html
    assert "Adresat:" in html
    assert reverse("legal:withdrawal") in page_text(client.get(reverse("legal:terms")))


@pytest.mark.django_db
def test_terms_promise_refunds(client):
    html = _text(page_text(client.get(reverse("legal:terms"))))

    assert "zwraca wtedy niewykorzystaną część opłaty" in html
    assert "wyłącznie z następujących ważnych przyczyn" in html
    assert "rozdziału 5b ustawy o prawach konsumenta" in html
