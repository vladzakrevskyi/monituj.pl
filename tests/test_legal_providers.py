import pytest
from django.urls import reverse

from tests.conftest import page_text


def _entity(settings, **values):
    settings.LEGAL_ENTITY = {**settings.LEGAL_ENTITY, **values}


@pytest.mark.django_db
def test_cdn_is_named_in_the_privacy_policy_and_the_dpa(client, settings):
    _entity(settings, cdn_provider="Cloudflare, Inc.")

    privacy = page_text(client.get(reverse("legal:privacy")))
    dpa = page_text(client.get(reverse("legal:dpa")))

    assert "(CDN): Cloudflare, Inc." in privacy
    assert "Ruch do Serwisu obsługuje Cloudflare, Inc." in privacy
    assert "(CDN) – Cloudflare, Inc." in dpa


@pytest.mark.django_db
def test_without_a_cdn_it_is_not_mentioned(client, settings):
    _entity(settings, cdn_provider="")

    privacy = page_text(client.get(reverse("legal:privacy")))
    dpa = page_text(client.get(reverse("legal:dpa")))

    assert "CDN" not in privacy
    assert "CDN" not in dpa


@pytest.mark.django_db
def test_an_email_address_is_never_published_as_a_provider(client, settings):
    _entity(
        settings,
        email_provider="support@euronodes.com",
        cdn_provider="noc@example.com",
    )

    privacy = page_text(client.get(reverse("legal:privacy")))

    assert "support@euronodes.com" not in privacy
    assert "[uzupełnij: dostawca poczty email]" in privacy
    assert "noc@example.com" not in privacy
