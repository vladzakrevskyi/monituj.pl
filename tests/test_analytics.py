import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import Client as BrowserClient
from django.urls import reverse

from apps.common.analytics import content_security_policy, gtm_id

GTM = "GTM-NWZ96857"


@pytest.fixture
def gtm(settings):
    settings.GTM_ID = GTM
    return GTM


def _html(path, **headers):
    # A fresh client builds a fresh middleware stack, so the CSP reflects
    # the current settings.
    return BrowserClient().get(path, **headers)


@pytest.mark.django_db
def test_nothing_is_loaded_without_a_container_id(settings):
    settings.GTM_ID = ""

    response = _html("/")

    assert "consent.js" not in response.content.decode()
    assert "googletagmanager" not in response["Content-Security-Policy"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path", ["/", "/cennik/", "/dla-kogo/kadry/", "/regulamin/", "/rejestracja/"]
)
def test_public_pages_load_the_consent_script(gtm, path):
    html = _html(path).content.decode()

    assert f'data-gtm-id="{GTM}"' in html
    assert "js/consent.js" in html
    assert "data-cookie-settings" in html


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path", ["/logowanie/", "/d/some-token/", "/dostep/wyslij/", "/reset-hasla/x/"]
)
def test_private_pages_and_token_links_never_load_it(gtm, path):
    html = _html(path).content.decode()

    assert "consent.js" not in html
    assert "googletagmanager" not in html


@pytest.mark.django_db
def test_panel_never_loads_it(gtm, user):
    browser = BrowserClient()
    browser.force_login(user)

    assert "consent.js" not in browser.get(reverse("accounts:panel")).content.decode()


@pytest.mark.django_db
def test_no_inline_script_is_needed(gtm):
    html = _html("/").content.decode()

    assert "(function(w,d,s,l,i)" not in html
    assert "<noscript><iframe" not in html


@pytest.mark.django_db
def test_content_security_policy_allows_only_google_tag_sources(gtm):
    header = _html("/")["Content-Security-Policy"]

    assert "script-src 'self' https://www.googletagmanager.com" in header
    assert "https://*.google-analytics.com" in header
    assert "'unsafe-inline'" not in header


def test_container_id_must_look_like_one(settings):
    settings.GTM_ID = "GTM-X';alert(1)//"

    with pytest.raises(ImproperlyConfigured):
        gtm_id()


def test_policy_is_unchanged_without_analytics(settings):
    settings.GTM_ID = ""

    assert content_security_policy() == settings.CONTENT_SECURITY_POLICY


@pytest.mark.django_db
def test_cookie_policy_describes_analytics_only_when_it_is_on(settings):
    settings.GTM_ID = ""
    off = _html(reverse("legal:cookies")).content.decode()
    settings.GTM_ID = GTM
    on = _html(reverse("legal:cookies")).content.decode()

    assert "_ga" not in off
    assert "wyłącznie plików cookies niezbędnych" in off.replace(" ", " ")
    assert "<code>_ga</code>" in on
    assert "Ustawienia cookies" in on
