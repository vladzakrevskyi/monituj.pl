"""The home page: what a visitor needs in the first seconds, the calculator,
the demo and the links that lead further."""

import re
from datetime import date

import pytest
from django.urls import reverse

from apps.common.pages import hero_example
from apps.common.seo import SOCIAL_LINKS


def _html(client):
    return client.get(reverse("landing")).content.decode()


@pytest.mark.django_db
def test_header_offers_login_demo_and_sign_up_to_visitors(client):
    html = _html(client)
    header = html[html.index('class="lp-page lp-header"') : html.index("</header>")]

    assert f'class="lp-nav__login" href="{reverse("accounts:login")}"' in header
    assert f'href="{reverse("pages:demo")}"' in header
    assert f'href="{reverse("accounts:register")}"' in header
    assert 'data-nav-toggle="#lp-menu"' in header


@pytest.mark.django_db
def test_header_takes_a_signed_in_user_to_the_panel(client, user):
    client.force_login(user)
    html = _html(client)
    header = html[html.index('class="lp-page lp-header"') : html.index("</header>")]

    assert f'href="{reverse("accounts:panel")}"' in header
    assert reverse("accounts:login") not in header


@pytest.mark.django_db
def test_home_page_has_the_working_calculator(client):
    html = _html(client)

    assert 'id="kalkulator"' in html
    for name in ("clients", "times", "minutes", "rate"):
        assert f'data-input="{name}"' in html
        assert f'data-show="{name}"' in html
    for name in ("hours", "money", "plan", "payback"):
        assert f'data-out="{name}"' in html
    assert 'id="calculator-plans" type="application/json"' in html
    assert "js/calculator.js" in html


@pytest.mark.django_db
def test_fonts_come_from_our_own_server(client):
    html = _html(client)

    assert "css/marketing.css" in html
    assert "fonts/funnel-display-latin.woff2" in html
    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html


@pytest.mark.django_db
def test_footer_links_to_the_social_profiles(client):
    footer = _html(client).split('class="lp-page lp-footer"')[1]

    for link in SOCIAL_LINKS:
        assert f'href="{link["url"]}"' in footer


@pytest.mark.parametrize(
    "today, month, due, first, last",
    [
        (date(2026, 11, 6), "wrzesień", "10.10", "01.10", "08.10"),
        (date(2026, 1, 31), "listopad", "10.12", "01.12", "08.12"),
        (date(2026, 3, 1), "styczeń", "10.02", "01.02", "08.02"),
    ],
)
def test_hero_example_is_always_in_the_past(today, month, due, first, last):
    example = hero_example(today)

    assert example["month"] == month
    assert example["due"] == due
    assert example["days"][0] == first
    assert example["days"][-1] == last


@pytest.mark.django_db
def test_hero_card_shows_this_months_example(client):
    # The site's typography glues short words to the next one.
    html = _html(client).replace("\xa0", " ")

    assert re.search(r"Dokumenty za [a-zśźńż]+</p>", html)
    assert "Komplet. Przypomnienia zatrzymane." in html
