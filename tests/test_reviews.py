""" "Oceń Monituj": a month after signing up, once more a month later unless
the link was clicked or the owner said no - and only once the privacy
policy saying so is in force."""

from datetime import date, timedelta

import pytest
from django.test import Client as HttpClient
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.notifications import reviews
from apps.notifications.models import ReviewInvite

NOW = timezone.now()


@pytest.fixture
def in_force(settings, monkeypatch):
    settings.LEGAL_VERSIONS = {
        **settings.LEGAL_VERSIONS,
        "polityka_prywatnosci": "2020-01-01",
    }
    monkeypatch.setattr(reviews, "REVIEWS_SINCE", date(2020, 1, 1))


def _account(email="owner@example.com", days=31, verified=True):
    return User.objects.create_user(
        email=email,
        password="x",
        date_joined=NOW - timedelta(days=days),
        email_verified_at=NOW if verified else None,
    )


def _later(days):
    return NOW + timedelta(days=days)


@pytest.mark.django_db
def test_a_month_old_account_is_asked_once(in_force, mailoutbox):
    owner = _account()
    _account("nowy@example.com", days=10)
    _account("niepotwierdzony@example.com", verified=False)

    assert reviews.send_due() == 1
    assert reviews.send_due() == 0  # not again the same day

    assert [m.to for m in mailoutbox] == [[owner.email]]
    message = mailoutbox[0]
    invite = ReviewInvite.objects.get(user=owner)
    assert f"/opinia/{invite.token}/" in message.body
    assert message.extra_headers["List-Unsubscribe-Post"] == (
        "List-Unsubscribe=One-Click"
    )
    assert (
        f"/opinia/{invite.token}/rezygnacja/"
        in message.extra_headers["List-Unsubscribe"]
    )


@pytest.mark.django_db
def test_asked_again_a_month_later_and_never_a_third_time(in_force, mailoutbox):
    _account()

    reviews.send_due()
    assert reviews.send_due(_later(20)) == 0
    assert reviews.send_due(_later(31)) == 1
    assert reviews.send_due(_later(62)) == 0

    assert len(mailoutbox) == 2
    assert "Masz minutę" in mailoutbox[1].subject


@pytest.mark.django_db
def test_a_click_ends_it(in_force, client, settings):
    owner = _account()
    reviews.send_due()
    invite = ReviewInvite.objects.get(user=owner)

    response = client.get(reverse("notifications:review", args=[invite.token]))

    assert response.status_code == 302
    assert response.url == settings.TRUSTPILOT_REVIEW_URL
    invite.refresh_from_db()
    assert invite.clicked_at is not None
    assert reviews.send_due(_later(31)) == 0


@pytest.mark.django_db
def test_saying_no_ends_it_but_a_bare_visit_does_not(in_force):
    owner = _account()
    reviews.send_due()
    invite = ReviewInvite.objects.get(user=owner)
    url = reverse("notifications:review-stop", args=[invite.token])
    # As a mail app's one-click unsubscribe: no session, no CSRF token.
    browser = HttpClient(enforce_csrf_checks=True)

    browser.get(url)
    invite.refresh_from_db()
    assert invite.declined_at is None

    response = browser.post(url)
    assert "Nie będziemy już prosić" in response.content.decode()
    invite.refresh_from_db()
    assert invite.declined_at is not None
    assert reviews.send_due(_later(31)) == 0


@pytest.mark.django_db
def test_demo_accounts_are_never_asked(in_force):
    from apps.demo.models import DemoAccount

    demo = _account("demo@example.com")
    DemoAccount.objects.create(user=demo, expires_at=_later(1))

    assert reviews.send_due() == 0


@pytest.mark.django_db
def test_nothing_before_the_privacy_policy_says_so(settings, mailoutbox):
    settings.LEGAL_VERSIONS = {
        **settings.LEGAL_VERSIONS,
        "polityka_prywatnosci": "2026-09-29",
    }
    _account()

    assert not reviews.allowed()
    assert reviews.send_due() == 0
    assert mailoutbox == []


@pytest.mark.django_db
def test_an_unknown_link_still_leads_to_trustpilot(client, settings):
    response = client.get(reverse("notifications:review", args=["nieznany"]))

    assert response.url == settings.TRUSTPILOT_REVIEW_URL
