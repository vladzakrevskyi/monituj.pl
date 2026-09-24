import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.reminders.models import Reminder


@pytest.mark.django_db
def test_send_manual_reminder_requires_login(client, request_record):
    response = client.post(
        reverse("reminders_api:send-manual", args=[request_record.pk])
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_send_manual_reminder_succeeds(client, user, request_record):
    client.force_login(user)

    response = client.post(
        reverse("reminders_api:send-manual", args=[request_record.pk])
    )

    assert response.status_code == 200
    assert response.json()["data"]["sent"] is True
    assert Reminder.objects.filter(request=request_record).exists()


@pytest.mark.django_db
def test_send_manual_reminder_denies_cross_owner_request(client, request_record):
    other = User.objects.create_user(email="stranger@example.com", password="x")
    client.force_login(other)

    response = client.post(
        reverse("reminders_api:send-manual", args=[request_record.pk])
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_send_manual_reminder_blocks_double_click(client, user, request_record):
    client.force_login(user)
    reverse_url = reverse("reminders_api:send-manual", args=[request_record.pk])

    first = client.post(reverse_url)
    second = client.post(reverse_url)

    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "REMINDER_TOO_SOON"
