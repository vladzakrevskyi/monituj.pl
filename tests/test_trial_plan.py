from datetime import timedelta

import pytest
from django.contrib.messages import get_messages
from django.core import mail
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccountToken, AccountTokenPurpose, User
from apps.billing import plans
from apps.billing.services import (
    SIGNUP_PLAN_SESSION_KEY,
    account_for,
    apply_signup_plan,
    state_for,
)
from apps.billing.tasks import send_trial_notices
from apps.common.security import generate_public_token, hash_token
from tests.conftest import page_text

PASSWORD = "Sup3r-Secret-Pass!"


def _register(client, email="nowy@example.com"):
    return client.post(
        reverse("accounts:register"),
        {
            "email": email,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "accept_terms": "on",
            "accept_privacy_policy": "on",
        },
    )


def _verify(client, user):
    raw = generate_public_token()
    AccountToken.objects.create(
        user=user,
        purpose=AccountTokenPurpose.EMAIL_VERIFICATION,
        token_hash=hash_token(raw),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    return client.post(reverse("accounts:verify-email", args=[raw]))


@pytest.mark.django_db
def test_pricing_buttons_carry_the_plan_to_signup(client):
    html = page_text(client.get(reverse("pages:pricing")))

    for plan in plans.PAID_PLANS:
        assert f"{reverse('accounts:register')}?plan={plan.code}" in html
        assert f"Wypróbuj {plan.name} za darmo" in html


@pytest.mark.django_db
def test_trial_is_of_the_plan_picked_on_the_pricing_page(client):
    page = page_text(client.get(reverse("accounts:register") + "?plan=pro"))
    _register(client)

    user = User.objects.get(email="nowy@example.com")
    state = state_for(user)
    assert "Plan Pro – 30 dni za darmo" in page
    assert (state.plan, state.source, state.limit) == (plans.PRO, "trial", 250)
    assert SIGNUP_PLAN_SESSION_KEY not in client.session


@pytest.mark.django_db
@pytest.mark.parametrize("code", ["", "free", "nieznany"])
def test_without_a_valid_pick_the_trial_is_biuro(client, code):
    client.get(reverse("accounts:register") + f"?plan={code}")
    _register(client)

    state = state_for(User.objects.get(email="nowy@example.com"))
    assert (state.plan, state.source) == (plans.BIURO, "trial")


@pytest.mark.django_db
def test_after_confirming_the_email_the_picked_plan_is_shown(client):
    client.get(reverse("accounts:register") + "?plan=start")
    _register(client)
    user = User.objects.get(email="nowy@example.com")

    response = _verify(client, user)

    assert response.url == reverse("billing:plan")
    text = " ".join(str(m) for m in get_messages(response.wsgi_request))
    assert "Masz 30 dni planu Start za darmo" in text.replace(" ", " ")


@pytest.mark.django_db
def test_without_a_pick_confirming_leads_to_the_panel(client):
    _register(client)

    response = _verify(client, User.objects.get(email="nowy@example.com"))

    assert response.url == reverse("accounts:panel")


@pytest.mark.django_db
def test_google_signup_keeps_the_pick(user):
    request = RequestFactory().get("/")
    request.session = {SIGNUP_PLAN_SESSION_KEY: "pro"}

    apply_signup_plan(user, request)

    assert state_for(user).plan == plans.PRO
    assert SIGNUP_PLAN_SESSION_KEY not in request.session


@pytest.mark.django_db
def test_plan_page_highlights_the_plan_being_tried(client, user):
    account = account_for(user)
    account.trial_plan = "pro"
    account.save()
    client.force_login(user)

    html = page_text(client.get(reverse("billing:plan")))

    pro_card = html.split('<h3 class="plan-card__name">Pro</h3>')[0].rsplit(
        "<article", 1
    )[1]
    assert "plan-card--featured" in pro_card
    assert "Plan Pro" in html  # sidebar meter


@pytest.mark.django_db
def test_trial_emails_name_the_plan_being_tried(user):
    user.email_verified_at = timezone.now()
    user.save()
    account = account_for(user)
    account.trial_plan = "start"
    account.trial_ends_at = timezone.now() + timedelta(days=3)
    account.save()

    send_trial_notices()

    assert "planu Start" in mail.outbox[0].body.replace(" ", " ")
