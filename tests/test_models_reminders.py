import pytest

from apps.reminders.models import Reminder, ReminderKind


@pytest.mark.django_db
def test_manual_reminder_records_triggering_user(request_record, user):
    reminder = Reminder.objects.create(
        request=request_record, kind=ReminderKind.MANUAL, triggered_by=user
    )

    assert reminder.kind == ReminderKind.MANUAL
    assert reminder.triggered_by == user


@pytest.mark.django_db
def test_automatic_reminder_has_no_triggering_user(request_record):
    reminder = Reminder.objects.create(
        request=request_record, kind=ReminderKind.AUTOMATIC
    )

    assert reminder.triggered_by is None
