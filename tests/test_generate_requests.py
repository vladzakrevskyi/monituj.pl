import pytest
from django.core import mail
from django.core.management import CommandError, call_command

from apps.requests.models import Request


@pytest.mark.django_db
def test_generates_requests_without_sending_anything(settings, user):
    settings.DEBUG = True

    call_command("generate_requests", email="OWNER@example.com", count=15, seed=1)

    requests = Request.objects.filter(created_by=user)
    assert requests.count() == 15
    assert all(r.client.email.endswith("@example.com") for r in requests)
    assert all(r.client.owner == user for r in requests)
    assert all(2 <= r.items.count() <= 6 for r in requests)
    assert not requests.filter(reminders_enabled=True).exists()
    assert mail.outbox == []


@pytest.mark.django_db
def test_refuses_unknown_account_and_production(settings, user):
    settings.DEBUG = True
    with pytest.raises(CommandError, match="No account"):
        call_command("generate_requests", email="nobody@example.com", count=1)

    settings.DEBUG = False
    with pytest.raises(CommandError, match="--force"):
        call_command("generate_requests", email=user.email, count=1)
