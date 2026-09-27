import pytest
from django.test import Client as Browser

from apps.accounts.models import User
from apps.audit.models import AuditEvent, AuditLog
from apps.common import admin_security

LOGIN = "/admin/login/"


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(
        email="root@example.com", password="Sup3r-Tajne!"
    )


def _try(browser, password, ip="83.1.1.1", email="root@example.com"):
    return browser.post(
        LOGIN,
        {"username": email, "password": password, "next": "/admin/"},
        REMOTE_ADDR=ip,
    )


@pytest.mark.django_db
def test_admin_login_stops_guessing(superuser):
    browser = Browser()
    for _ in range(admin_security.FAILURES_PER_LOGIN):
        assert _try(browser, "zgaduje").status_code == 200

    # Blocked now - even with the right password.
    blocked = _try(browser, "Sup3r-Tajne!")

    assert blocked.status_code == 429
    assert not browser.session.get("_auth_user_id")
    assert (
        AuditLog.objects.filter(event=AuditEvent.USER_LOGIN_FAILED).count()
        == admin_security.FAILURES_PER_LOGIN
    )


@pytest.mark.django_db
def test_admin_login_limit_per_address_across_names(superuser):
    browser = Browser()
    for index in range(admin_security.FAILURES_PER_IP):
        _try(browser, "x", email=f"kto{index}@example.com")

    assert _try(browser, "Sup3r-Tajne!").status_code == 429


@pytest.mark.django_db
def test_admin_login_still_works(superuser):
    browser = Browser()

    response = _try(browser, "Sup3r-Tajne!")

    assert response.status_code == 302
    assert browser.session.get("_auth_user_id") == str(superuser.pk)


@pytest.mark.django_db
def test_admin_is_invisible_outside_allowed_addresses(settings, superuser):
    settings.ADMIN_ALLOWED_IPS = ["83.12.34.0/24"]
    browser = Browser()  # a fresh middleware stack reads the setting

    assert browser.get("/admin/", REMOTE_ADDR="5.5.5.5").status_code == 404
    assert browser.get(LOGIN, REMOTE_ADDR="5.5.5.5").status_code == 404
    assert _try(browser, "Sup3r-Tajne!", ip="5.5.5.5").status_code == 404
    assert browser.get(LOGIN, REMOTE_ADDR="83.12.34.7").status_code == 200
    # Our proxy's address counts, not one the visitor writes in.
    assert (
        browser.get(
            LOGIN, REMOTE_ADDR="5.5.5.5", HTTP_X_FORWARDED_FOR="83.12.34.7, 5.5.5.5"
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_rest_of_the_site_ignores_the_admin_allowlist(settings):
    settings.ADMIN_ALLOWED_IPS = ["83.12.34.0/24"]

    assert Browser().get("/", REMOTE_ADDR="5.5.5.5").status_code == 200


@pytest.mark.django_db
def test_admin_is_never_indexed_nor_named_in_robots(client):
    assert client.get(LOGIN)["X-Robots-Tag"] == "noindex, nofollow"
    assert "/admin/" not in client.get("/robots.txt").content.decode()
