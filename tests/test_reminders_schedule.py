from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.reminders.models import Reminder, ReminderKind
from apps.reminders.schedule import recipient_zone, send_clock
from apps.reminders.services import ReminderScheduleService
from apps.requests.models import RecipientAccess, RequestItem, RequestItemStatus

WARSAW = ZoneInfo("Europe/Warsaw")
NEW_YORK = ZoneInfo("America/New_York")


def _at(tz, *args):
    return datetime(*args, tzinfo=tz)


def _configure(request_record, created_at, sender_timezone="Europe/Warsaw"):
    request_record.reminders_enabled = True
    request_record.first_reminder_after_days = 2
    request_record.reminder_frequency_days = 3
    request_record.max_reminders = 3
    request_record.sender_timezone = sender_timezone
    request_record.save()
    type(request_record).objects.filter(pk=request_record.pk).update(
        created_at=created_at
    )
    request_record.refresh_from_db()


@pytest.mark.django_db
def test_reminders_go_out_at_the_time_the_request_was_sent(
    request_record, request_item
):
    _configure(request_record, _at(WARSAW, 2026, 9, 1, 14, 20))

    planned = ReminderScheduleService.planned(
        request_record, now=_at(WARSAW, 2026, 9, 1, 15, 0)
    )

    assert planned == [
        _at(WARSAW, 2026, 9, 3, 14, 20),
        _at(WARSAW, 2026, 9, 6, 14, 20),
        _at(WARSAW, 2026, 9, 9, 14, 20),
    ]


@pytest.mark.django_db
def test_recipient_in_another_zone_gets_them_at_the_same_local_time(
    request_record, request_item
):
    _configure(request_record, _at(WARSAW, 2026, 9, 1, 14, 20))
    RecipientAccess.objects.create(
        email=request_record.client.email, timezone="America/New_York"
    )

    planned = ReminderScheduleService.planned(
        request_record, now=_at(WARSAW, 2026, 9, 1, 15, 0)
    )

    assert recipient_zone(request_record).key == "America/New_York"
    assert planned[0] == _at(NEW_YORK, 2026, 9, 3, 14, 20)


@pytest.mark.django_db
def test_sender_zone_decides_the_clock_time(request_record, request_item):
    # 14:20 in New York is 20:20 in Warsaw - the clock time is the sender's.
    _configure(
        request_record,
        _at(NEW_YORK, 2026, 9, 1, 14, 20),
        sender_timezone="America/New_York",
    )

    assert send_clock(request_record) == time(14, 20)


@pytest.mark.django_db
def test_night_times_move_into_the_day(request_record, request_item):
    _configure(request_record, _at(WARSAW, 2026, 9, 1, 23, 40))
    assert send_clock(request_record) == time(20, 0)

    _configure(request_record, _at(WARSAW, 2026, 9, 1, 5, 10))
    assert send_clock(request_record) == time(8, 0)


@pytest.mark.django_db
def test_planned_accounts_for_reminders_already_sent(request_record, request_item):
    _configure(request_record, _at(WARSAW, 2026, 9, 1, 10, 0))
    reminder = Reminder.objects.create(
        request=request_record, kind=ReminderKind.AUTOMATIC
    )
    Reminder.objects.filter(pk=reminder.pk).update(
        sent_at=_at(WARSAW, 2026, 9, 3, 10, 2)
    )

    planned = ReminderScheduleService.planned(
        request_record, now=_at(WARSAW, 2026, 9, 4, 12, 0)
    )

    assert planned == [
        _at(WARSAW, 2026, 9, 6, 10, 0),
        _at(WARSAW, 2026, 9, 9, 10, 0),
    ]


@pytest.mark.django_db
def test_overdue_reminder_is_shown_as_going_out_now(request_record, request_item):
    _configure(request_record, _at(WARSAW, 2026, 9, 1, 10, 0))
    now = _at(WARSAW, 2026, 9, 5, 12, 0)

    planned = ReminderScheduleService.planned(request_record, now=now)

    assert planned[0] == now


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
