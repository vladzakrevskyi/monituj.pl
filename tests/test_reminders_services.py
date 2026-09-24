from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core import mail
from django.utils import timezone

from apps.audit.models import AuditEvent, AuditLog
from apps.common.exceptions import ValidationAppError
from apps.documents.services import DocumentReviewService, UploadDocumentService
from apps.reminders.models import Reminder, ReminderKind
from apps.reminders.services import AutomaticReminderService, ReminderService
from apps.requests.models import Request
from tests.conftest import make_pdf_upload


@pytest.mark.django_db
def test_manual_reminder_creates_record_and_sends_email(user, request_record):
    reminder = ReminderService.send_manual(request_record, actor=user)

    assert reminder.kind == ReminderKind.MANUAL
    assert reminder.triggered_by == user
    assert reminder.sequence_number == 1
    assert AuditLog.objects.filter(event=AuditEvent.REMINDER_SENT).exists()
    assert any("Przypomnienie" in (m.subject or "") for m in mail.outbox)


@pytest.mark.django_db
def test_manual_reminder_blocked_when_request_complete(user, request_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    DocumentReviewService.accept(request_item)

    with pytest.raises(ValidationAppError) as exc_info:
        ReminderService.send_manual(request_item.request, actor=user)
    assert exc_info.value.code == "ALREADY_COMPLETE"


@pytest.mark.django_db
def test_manual_reminder_blocks_rapid_double_click(user, request_record):
    ReminderService.send_manual(request_record, actor=user)

    with pytest.raises(ValidationAppError) as exc_info:
        ReminderService.send_manual(request_record, actor=user)
    assert exc_info.value.code == "REMINDER_TOO_SOON"
    assert Reminder.objects.filter(request=request_record).count() == 1


@pytest.mark.django_db
def test_manual_reminder_sequence_increments(user, request_record):
    ReminderService.send_manual(request_record, actor=user)
    Reminder.objects.filter(request=request_record).update(
        sent_at=timezone.now() - timedelta(minutes=1)
    )

    second = ReminderService.send_manual(request_record, actor=user)
    assert second.sequence_number == 2


@pytest.mark.django_db
def test_automatic_reminder_not_due_yet(request_record):
    sent = AutomaticReminderService.maybe_send_for_request(request_record.pk)
    assert sent is False
    assert not Reminder.objects.filter(request=request_record).exists()


@pytest.mark.django_db
def test_automatic_reminder_sends_when_due_and_past_send_hour(request_record):
    request_record.first_reminder_after_days = 2
    request_record.reminder_send_hour = 0
    request_record.save()
    Request.objects.filter(pk=request_record.pk).update(
        created_at=timezone.now() - timedelta(days=3)
    )

    sent = AutomaticReminderService.maybe_send_for_request(request_record.pk)

    assert sent is True
    reminder = Reminder.objects.get(request=request_record)
    assert reminder.kind == ReminderKind.AUTOMATIC
    assert reminder.sequence_number == 1
    assert reminder.triggered_by is None


@pytest.mark.django_db
def test_automatic_reminder_waits_for_configured_send_hour(request_record):
    request_record.first_reminder_after_days = 2
    request_record.reminder_send_hour = 20
    request_record.save()
    Request.objects.filter(pk=request_record.pk).update(
        created_at=timezone.now() - timedelta(days=3)
    )
    morning = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)

    with patch("apps.reminders.services.timezone.now", return_value=morning):
        sent = AutomaticReminderService.maybe_send_for_request(request_record.pk)
    assert sent is False

    evening = morning.replace(hour=21)
    with patch("apps.reminders.services.timezone.now", return_value=evening):
        sent = AutomaticReminderService.maybe_send_for_request(request_record.pk)
    assert sent is True


@pytest.mark.django_db
def test_automatic_reminder_respects_max_reminders(request_record):
    request_record.max_reminders = 1
    request_record.reminder_send_hour = 0
    request_record.save()
    Reminder.objects.create(
        request=request_record,
        kind=ReminderKind.AUTOMATIC,
        sequence_number=1,
    )
    Reminder.objects.filter(request=request_record).update(
        sent_at=timezone.now() - timedelta(days=30)
    )

    sent = AutomaticReminderService.maybe_send_for_request(request_record.pk)
    assert sent is False


@pytest.mark.django_db
def test_automatic_reminder_stops_when_complete(request_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    DocumentReviewService.accept(request_item)
    request_obj = request_item.request
    request_obj.reminder_send_hour = 0
    request_obj.save()
    Request.objects.filter(pk=request_obj.pk).update(
        created_at=timezone.now() - timedelta(days=30)
    )

    sent = AutomaticReminderService.maybe_send_for_request(request_obj.pk)
    assert sent is False


@pytest.mark.django_db
def test_automatic_reminder_respects_disabled_flag(request_record):
    request_record.reminders_enabled = False
    request_record.reminder_send_hour = 0
    request_record.save()
    Request.objects.filter(pk=request_record.pk).update(
        created_at=timezone.now() - timedelta(days=30)
    )

    sent = AutomaticReminderService.maybe_send_for_request(request_record.pk)
    assert sent is False


@pytest.mark.django_db
def test_automatic_reminder_second_reminder_based_on_last_automatic_sent_at(
    request_record,
):
    request_record.reminder_send_hour = 0
    request_record.reminder_frequency_days = 3
    request_record.save()
    Reminder.objects.create(
        request=request_record, kind=ReminderKind.AUTOMATIC, sequence_number=1
    )
    Reminder.objects.filter(request=request_record).update(
        sent_at=timezone.now() - timedelta(days=1)
    )

    sent = AutomaticReminderService.maybe_send_for_request(request_record.pk)
    assert sent is False

    Reminder.objects.filter(request=request_record).update(
        sent_at=timezone.now() - timedelta(days=4)
    )
    sent = AutomaticReminderService.maybe_send_for_request(request_record.pk)
    assert sent is True
    assert Reminder.objects.filter(request=request_record).count() == 2


@pytest.mark.django_db
def test_automatic_reminder_is_idempotent_when_called_twice_in_a_row(request_record):
    request_record.reminder_send_hour = 0
    request_record.save()
    Request.objects.filter(pk=request_record.pk).update(
        created_at=timezone.now() - timedelta(days=30)
    )

    first = AutomaticReminderService.maybe_send_for_request(request_record.pk)
    second = AutomaticReminderService.maybe_send_for_request(request_record.pk)

    assert first is True
    assert second is False
    assert Reminder.objects.filter(request=request_record).count() == 1


@pytest.mark.django_db
def test_automatic_reminder_returns_false_for_unknown_request():
    assert AutomaticReminderService.maybe_send_for_request(999999) is False


@pytest.mark.django_db
def test_manual_and_automatic_reminders_have_independent_sequence_counts(
    user, request_record
):
    ReminderService.send_manual(request_record, actor=user)
    request_record.reminder_send_hour = 0
    request_record.save()
    Request.objects.filter(pk=request_record.pk).update(
        created_at=timezone.now() - timedelta(days=30)
    )

    AutomaticReminderService.maybe_send_for_request(request_record.pk)

    automatic = Reminder.objects.get(
        request=request_record, kind=ReminderKind.AUTOMATIC
    )
    assert automatic.sequence_number == 1
