import json
import re

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import Client as BrowserClient
from django.urls import reverse

from apps.common import cookies

GTM = "GTM-NWZ96857"
DIRECTIVES = {
    "script-src",
    "img-src",
    "connect-src",
    "frame-src",
    "style-src",
    "font-src",
}


@pytest.fixture
def tracking(settings):
    def switch_on(*services):
        settings.GTM_ID = GTM
        settings.TRACKING_SERVICES = list(services)

    return switch_on


def _get(path):
    # A fresh client builds a fresh middleware stack, so the CSP reflects
    # the current settings.
    return BrowserClient().get(path)


def _text(response):
    return response.content.decode().replace(" ", " ")


def _config(html):
    block = re.search(
        r'<script id="cookie-consent-config" type="application/json">(.*?)</script>',
        html,
        re.S,
    )
    return json.loads(block.group(1)) if block else None


@pytest.mark.parametrize("key", list(cookies.SERVICES))
def test_every_service_is_fully_described(key):
    service = cookies.SERVICES[key]

    assert service["category"] in cookies.CATEGORIES
    assert not cookies.CATEGORIES[service["category"]].get("required")
    assert service["policy_url"].startswith("https://")
    for field in ("name", "provider", "purpose", "data", "retention"):
        assert service[field], field
    assert service["cookies"]
    for entry in service["cookies"]:
        assert len(entry) in (3, 4), entry
    assert set(service["csp"]) <= DIRECTIVES
    for sources in service["csp"].values():
        assert all(source.startswith("https://") for source in sources)


def test_unknown_service_is_refused(tracking):
    tracking("ga4", "tiktok")

    with pytest.raises(ImproperlyConfigured):
        cookies.consent()


def test_without_gtm_no_service_runs(settings):
    settings.GTM_ID = ""
    settings.TRACKING_SERVICES = ["ga4", "meta_pixel"]

    consent = cookies.consent()

    assert consent["enabled"] is False
    assert [c["key"] for c in consent["categories"]] == ["necessary"]
    assert cookies.csp_sources() == {}


def test_join_pl():
    assert cookies.join_pl(["a"]) == "a"
    assert cookies.join_pl(["a", "b"]) == "a i b"
    assert cookies.join_pl(["a", "b", "c"]) == "a, b i c"


def test_changing_the_tools_asks_visitors_again(tracking):
    tracking("ga4")
    before = cookies.consent()["config"]["version"]
    tracking("ga4", "meta_pixel")
    after = cookies.consent()["config"]["version"]
    tracking("meta_pixel", "ga4")

    assert before != after
    assert cookies.consent()["config"]["version"] == after


@pytest.mark.django_db
def test_only_categories_with_a_tool_are_offered(tracking):
    tracking("ga4")

    html = _text(_get("/"))
    config = _config(html)

    assert list(config["categories"]) == ["analytics"]
    assert config["categories"]["analytics"]["consent"] == ["analytics_storage"]
    assert config["categories"]["analytics"]["cookies"] == ["_ga", "_ga_*"]
    assert "cookies analitycznych (Google Analytics 4)" in html
    assert 'data-consent-category="analytics"' in html
    assert 'data-consent-category="marketing"' not in html
    assert "Zawsze aktywne" in html


@pytest.mark.django_db
def test_adding_a_marketing_tool_updates_banner_policies_and_csp(tracking):
    tracking("ga4", "meta_pixel")

    response = _get("/")
    html = _text(response)
    config = _config(html)
    cookie_policy = _text(_get(reverse("legal:cookies")))
    privacy = _text(_get(reverse("legal:privacy")))

    assert list(config["categories"]) == ["analytics", "marketing"]
    assert config["categories"]["marketing"]["consent"] == [
        "ad_storage",
        "ad_user_data",
        "ad_personalization",
    ]
    # Cookies on facebook.com can't be removed from our pages.
    assert config["categories"]["marketing"]["cookies"] == ["_fbp"]
    assert "cookies analitycznych i marketingowych" in html
    assert 'data-consent-category="marketing"' in html
    assert "https://connect.facebook.net" in response["Content-Security-Policy"]
    assert "<code>_fbp</code>" in cookie_policy
    assert "Cookies marketingowe – tylko za zgodą" in cookie_policy
    assert "Meta Platforms Ireland Ltd. (Meta Pixel)" in privacy
    assert "Meta Pixel – Meta Platforms, Inc. (USA)" in privacy


@pytest.mark.django_db
def test_frames_are_allowed_only_for_tools_that_need_them(tracking):
    tracking("ga4")
    assert "frame-src" not in _get("/")["Content-Security-Policy"]

    tracking("ga4", "google_ads")
    header = _get("/")["Content-Security-Policy"]

    # A directive missing from the base policy starts from default-src.
    assert "frame-src 'self' https://bid.g.doubleclick.net" in header


@pytest.mark.django_db
def test_banner_is_hidden_until_the_script_decides(tracking):
    tracking("ga4")

    html = _get("/").content.decode()

    assert re.search(r'<div class="cookie-banner"[^>]*\shidden>', html)
    assert "data-nosnippet" in html


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/logowanie/", "/d/some-token/", "/dostep/wyslij/"])
def test_private_pages_get_neither_banner_nor_config(tracking, path):
    tracking("ga4", "meta_pixel")

    html = _get(path).content.decode()

    assert "data-cookie-banner" not in html
    assert "cookie-consent-config" not in html


@pytest.mark.django_db
def test_policies_without_tools_say_only_necessary_cookies(settings):
    settings.GTM_ID = ""

    cookie_policy = _text(_get(reverse("legal:cookies")))
    privacy = _text(_get(reverse("legal:privacy")))

    assert "wyłącznie plików cookies niezbędnych" in cookie_policy
    assert "<code>sessionid</code>" in cookie_policy
    assert "monituj-consent" not in cookie_policy
    assert "Google Tag Manager" not in privacy
    assert "wyłącznie niezbędnych plików cookies" in privacy


@pytest.mark.django_db
def test_public_pages_are_locked_until_the_visitor_decides(tracking):
    tracking("ga4")

    html = _get("/").content.decode()

    assert "data-cookie-overlay" in html
    assert "{#" not in html and "Shown by" not in html
    assert re.search(r'data-cookie-banner data-cookie-lock[^>]*aria-modal="true"', html)


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["legal:cookies", "legal:privacy"])
def test_policies_stay_readable_before_deciding(tracking, name):
    tracking("ga4")

    html = _get(reverse(name)).content.decode()

    assert "data-cookie-banner" in html
    assert "data-cookie-lock" not in html
    assert "data-cookie-overlay" not in html
