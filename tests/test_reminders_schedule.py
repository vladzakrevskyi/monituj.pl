from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from apps.reminders.models import Reminder, ReminderKind
from apps.reminders.services import ReminderScheduleService
from apps.requests.models import RequestItem, RequestItemStatus


def _local(*args):
    return timezone.make_aware(datetime(*args))


def _configure(request_record, created_at):
    request_record.reminders_enabled = True
    request_record.first_reminder_after_days = 2
    request_record.reminder_frequency_days = 3
    request_record.max_reminders = 3
    request_record.reminder_send_hour = 9
    request_record.save()
    type(request_record).objects.filter(pk=request_record.pk).update(
        created_at=created_at
    )
    request_record.refresh_from_db()


@pytest.mark.django_db
def test_planned_lists_every_remaining_reminder_at_the_send_hour(
    request_record, request_item
):
    _configure(request_record, _local(2026, 9, 1, 7, 30))

    planned = ReminderScheduleService.planned(
        request_record, now=_local(2026, 9, 1, 8, 0)
    )

    assert planned == [
        _local(2026, 9, 3, 9, 0),
        _local(2026, 9, 6, 9, 0),
        _local(2026, 9, 9, 9, 0),
    ]


@pytest.mark.django_db
def test_planned_accounts_for_reminders_already_sent(request_record, request_item):
    _configure(request_record, _local(2026, 9, 1, 7, 30))
    reminder = Reminder.objects.create(
        request=request_record, kind=ReminderKind.AUTOMATIC
    )
    Reminder.objects.filter(pk=reminder.pk).update(sent_at=_local(2026, 9, 3, 9, 0))

    planned = ReminderScheduleService.planned(
        request_record, now=_local(2026, 9, 4, 12, 0)
    )

    assert planned == [_local(2026, 9, 6, 9, 0), _local(2026, 9, 9, 9, 0)]


@pytest.mark.django_db
def test_planned_due_after_send_hour_goes_out_at_next_full_hour(
    request_record, request_item
):
    _configure(request_record, _local(2026, 9, 1, 14, 20))

    planned = ReminderScheduleService.planned(
        request_record, now=_local(2026, 9, 1, 15, 0)
    )

    assert planned[0] == _local(2026, 9, 3, 15, 0)


@pytest.mark.django_db
def test_planned_empty_when_reminders_disabled(request_record, request_item):
    request_record.reminders_enabled = False
    request_record.save()

    assert ReminderScheduleService.planned(request_record) == []


@pytest.mark.django_db
def test_planned_empty_when_all_documents_delivered(request_record, request_item):
    _configure(request_record, timezone.now() - timedelta(days=1))
    RequestItem.objects.filter(pk=request_item.pk).update(
        status=RequestItemStatus.DOSTARCZONY
    )

    assert ReminderScheduleService.planned(request_record) == []
