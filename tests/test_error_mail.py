import logging

import pytest
from django.core import mail
from django.core.cache import cache
from django.test import RequestFactory

from apps.common import error_mail


@pytest.fixture
def admins(settings):
    settings.ADMINS = ["bledy@example.com"]
    settings.DEBUG = False
    cache.clear()
    yield
    cache.clear()


def _crash(logger="django.request", request=None):
    try:
        {}["brak"]
    except KeyError:
        logging.getLogger(logger).error(
            "Internal Server Error: /panel/", exc_info=True, extra={"request": request}
        )


def test_a_crash_is_emailed_without_the_request_data(admins, django_user_model):
    request = RequestFactory().post(
        "/panel/", {"client_email": "klient@firma.pl", "note": "tajne"}
    )

    _crash(request=request)

    [message] = mail.outbox
    assert message.to == ["bledy@example.com"]
    assert message.subject == "[Monituj] Błąd: Internal Server Error: /panel/"
    assert "POST /panel/" in message.body
    assert "KeyError" in message.body
    # Clients' data from the form never leaves in the email.
    assert "klient@firma.pl" not in message.body
    assert "tajne" not in message.body


def test_the_same_error_is_emailed_once_per_ten_minutes(admins):
    for _ in range(5):
        _crash()

    assert len(mail.outbox) == 1


def test_failed_background_tasks_and_app_errors_are_emailed(admins):
    logging.getLogger("celery.app.trace").error("Task send_notices raised")
    logging.getLogger("monituj").error("Stripe refund for cus_1 failed")

    assert [m.subject for m in mail.outbox] == [
        "[Monituj] Błąd: Task send_notices raised",
        "[Monituj] Błąd: Stripe refund for cus_1 failed",
    ]


def test_warnings_and_4xx_are_not_emailed(admins):
    logging.getLogger("django.request").warning("Not Found: /nic/")
    logging.getLogger("monituj").warning("Something odd")

    assert mail.outbox == []


def test_no_flood(admins, monkeypatch):
    monkeypatch.setattr(error_mail, "MAX_PER_HOUR", 3)

    for number in range(10):
        logging.getLogger("monituj").error(f"Different error {number}")

    assert len(mail.outbox) == 3
