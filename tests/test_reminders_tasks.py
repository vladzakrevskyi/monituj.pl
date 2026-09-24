from datetime import timedelta

import pytest
from django.utils import timezone

from apps.reminders.models import Reminder
from apps.reminders.tasks import send_automatic_reminders
from apps.requests.models import Request


@pytest.mark.django_db
def test_task_sends_reminders_for_due_requests_and_skips_others(user, client_record):
    from apps.requests.services import RequestService

    due = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Due",
        description="",
        deadline=None,
        item_names=["A"],
    )
    due.reminder_send_hour = 0
    due.save()
    Request.objects.filter(pk=due.pk).update(
        created_at=timezone.now() - timedelta(days=30)
    )

    not_due = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Not due",
        description="",
        deadline=None,
        item_names=["A"],
    )

    sent_count = send_automatic_reminders()

    assert sent_count == 1
    assert Reminder.objects.filter(request=due).exists()
    assert not Reminder.objects.filter(request=not_due).exists()


@pytest.mark.django_db
def test_task_runs_without_error_when_no_requests_exist():
    assert send_automatic_reminders() == 0
