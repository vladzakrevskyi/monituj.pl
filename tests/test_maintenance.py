import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.urls import reverse

from apps.common.maintenance import is_allowed, parse_networks


def _on(ips=""):
    return override_settings(
        MAINTENANCE_MODE=True,
        MAINTENANCE_ALLOWED_IPS=[ip for ip in ips.split(",") if ip],
    )


@pytest.mark.django_db
def test_site_works_normally_when_maintenance_is_off(client):
    response = client.get(reverse("pages:faq"))

    assert response.status_code == 200
    assert b"maintenance-bar" not in response.content


@pytest.mark.django_db
def test_visitors_see_the_maintenance_page(client):
    with _on():
        response = client.get(reverse("pages:faq"))

    assert response.status_code == 503
    assert response["Retry-After"]
    assert "Prace techniczne" in response.content.decode()
    assert "Content-Security-Policy" in response


@pytest.mark.django_db
def test_every_page_and_form_is_blocked(client, user):
    client.force_login(user)
    with _on():
        panel = client.get(reverse("accounts:panel"))
        login = client.post(reverse("accounts:login"), {"email": "a@b.pl"})

    assert panel.status_code == 503
    assert login.status_code == 503


@pytest.mark.django_db
def test_api_gets_a_json_error(client):
    with _on():
        response = client.get("/api/clients/")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MAINTENANCE"


@pytest.mark.django_db
def test_health_check_keeps_working(client):
    with _on():
        response = client.get(reverse("health-check"))

    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["billing:webhook", "billing:infakt-webhook"])
def test_payment_webhooks_keep_working(client, name):
    # Reaches the webhook itself (which refuses an unsigned call), not the
    # maintenance page.
    with _on():
        response = client.post(reverse(name), "{}", content_type="application/json")

    assert response.status_code != 503
    assert b"Prace techniczne" not in response.content


@pytest.mark.django_db
def test_listed_ips_use_the_site_and_see_a_reminder(client):
    with _on("83.12.34.56,10.0.0.0/24"):
        exact = client.get(reverse("pages:faq"), REMOTE_ADDR="83.12.34.56")
        in_range = client.get(reverse("pages:faq"), REMOTE_ADDR="10.0.0.77")
        other = client.get(reverse("pages:faq"), REMOTE_ADDR="83.12.34.57")

    assert exact.status_code == 200
    assert b"maintenance-bar" in exact.content
    assert in_range.status_code == 200
    assert other.status_code == 503


@pytest.mark.django_db
def test_address_comes_from_the_proxy_header(client):
    with _on("83.12.34.56"):
        response = client.get(
            reverse("pages:faq"),
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_FORWARDED_FOR="83.12.34.56",
        )

    assert response.status_code == 200


def test_ipv6_addresses_and_ranges_are_supported():
    networks = parse_networks(["2a01:4f8::1", "2001:db8::/32"])

    assert is_allowed("2a01:4f8::1", networks)
    assert is_allowed("2001:db8:1::5", networks)
    assert not is_allowed("2a01:4f8::2", networks)
    assert not is_allowed("nie-ip", networks)


def test_a_typo_in_the_list_stops_the_app_with_a_clear_error():
    with pytest.raises(ImproperlyConfigured, match="83.12.34"):
        parse_networks(["83.12.34"])


@pytest.mark.django_db
def test_maintenance_page_shows_the_visitors_address(client):
    with _on("10.0.0.1"):
        ipv4 = client.get(reverse("pages:faq"), HTTP_X_FORWARDED_FOR="83.7.253.70")
        ipv6 = client.get(
            reverse("pages:faq"),
            HTTP_X_FORWARDED_FOR="2a01:110f:1234:5678:abcd:ef01:2345:6789",
        )

    assert "Twój adres IP: <code>83.7.253.70</code>" in ipv4.content.decode()
    html = ipv6.content.decode()
    assert "<code>2a01:110f:1234:5678:abcd:ef01:2345:6789</code>" in html
    # Home IPv6 addresses change within the network - that is what to allow.
    assert "<code>2a01:110f:1234:5678::/64</code>" in html
