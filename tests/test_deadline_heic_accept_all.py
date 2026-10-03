"""Reminders before the deadline, iPhone photos (HEIC) stored as JPG, and
"Zaakceptuj wszystkie"."""

import io
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.documents.models import Document
from apps.documents.services import UploadDocumentService
from apps.reminders.models import Reminder, ReminderKind
from apps.reminders.schedule import deadline_dates
from apps.reminders.services import (
    AutomaticReminderService,
    DeadlineReminderService,
    ReminderScheduleService,
)
from apps.requests.models import RequestItemStatus
from tests.conftest import make_pdf_upload

# --- reminders before the deadline --------------------------------------------------


@pytest.fixture
def due_in_ten_days(request_record, request_item):
    """Sent 10 days ago, due in 10 days, nothing delivered."""
    from datetime import datetime, time

    from apps.requests.models import Request

    now = timezone.now()
    # As the form sets it: the end of the day.
    deadline = timezone.make_aware(
        datetime.combine(timezone.localdate() + timedelta(days=10), time.max)
    )
    Request.objects.filter(pk=request_record.pk).update(
        created_at=now - timedelta(days=10), deadline=deadline
    )
    request_record.refresh_from_db()
    return request_record


def _send(request_obj, at):
    return DeadlineReminderService.maybe_send_for_request(request_obj.pk, now=at)


@pytest.mark.django_db
def test_two_days_before_and_on_the_day(due_in_ten_days, mailoutbox):
    (_, before), (_, on_the_day) = deadline_dates(due_in_ten_days)

    assert not _send(due_in_ten_days, before - timedelta(minutes=5))
    assert _send(due_in_ten_days, before + timedelta(minutes=5))
    assert not _send(due_in_ten_days, before + timedelta(minutes=10))  # once
    assert _send(due_in_ten_days, on_the_day + timedelta(minutes=5))

    subjects = [m.subject for m in mailoutbox]
    assert subjects[0].startswith("Za 2 dni mija termin przesłania dokumentów")
    assert subjects[1].startswith("Dziś mija termin przesłania dokumentów")
    assert Reminder.objects.filter(kind=ReminderKind.DEADLINE).count() == 2


@pytest.mark.django_db
def test_not_right_after_another_reminder(due_in_ten_days, mailoutbox):
    (_, before), _ = deadline_dates(due_in_ten_days)
    reminder = Reminder.objects.create(
        request=due_in_ten_days, kind=ReminderKind.AUTOMATIC
    )
    Reminder.objects.filter(pk=reminder.pk).update(sent_at=before - timedelta(hours=3))

    assert not _send(due_in_ten_days, before + timedelta(minutes=5))
    assert mailoutbox == []


@pytest.mark.django_db
def test_nothing_when_complete_off_or_without_deadline(due_in_ten_days, request_item):
    (_, before), _ = deadline_dates(due_in_ten_days)
    at = before + timedelta(minutes=5)

    due_in_ten_days.reminders_enabled = False
    due_in_ten_days.save()
    assert not _send(due_in_ten_days, at)
    due_in_ten_days.reminders_enabled = True
    due_in_ten_days.save()
    request_item.status = RequestItemStatus.DOSTARCZONY
    request_item.save()
    assert not _send(due_in_ten_days, at)
    request_item.status = RequestItemStatus.BRAK
    request_item.save()
    due_in_ten_days.deadline = None
    due_in_ten_days.save()
    assert not _send(due_in_ten_days, at)


@pytest.mark.django_db
def test_a_missed_one_is_not_sent_late(due_in_ten_days):
    (_, before), _ = deadline_dates(due_in_ten_days)

    assert not _send(due_in_ten_days, before + timedelta(hours=13))


@pytest.mark.django_db
def test_planned_shows_them_and_interval_reminders_count_from_them(due_in_ten_days):
    (_, before), (_, on_the_day) = deadline_dates(due_in_ten_days)
    planned = ReminderScheduleService.planned(due_in_ten_days, now=timezone.now())

    assert before in planned and on_the_day in planned
    # After a deadline reminder, the next interval one waits its days.
    _send(due_in_ten_days, before + timedelta(minutes=5))
    deadline_reminder = Reminder.objects.get(kind=ReminderKind.DEADLINE)
    Reminder.objects.filter(pk=deadline_reminder.pk).update(
        sent_at=timezone.now() - timedelta(hours=1)
    )
    assert not AutomaticReminderService.maybe_send_for_request(due_in_ten_days.pk)


# --- iPhone photos -----------------------------------------------------------------


def _heic(width=64, height=48):
    import pillow_heif
    from PIL import Image

    pillow_heif.register_heif_opener()
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (200, 100, 50)).save(buffer, format="HEIF")
    return SimpleUploadedFile("IMG_1234.HEIC", buffer.getvalue())


@pytest.mark.django_db
def test_heic_photo_is_stored_as_jpg(request_item):
    from apps.documents.storage import read_document_file

    document = UploadDocumentService.upload_for_item(request_item, _heic())

    assert document.original_filename == "IMG_1234.jpg"
    assert document.content_type == "image/jpeg"
    assert read_document_file(document)[:3] == b"\xff\xd8\xff"  # a JPEG


@pytest.mark.django_db
def test_a_fake_heic_is_refused(request_item):
    from apps.common.exceptions import ValidationAppError

    with pytest.raises(ValidationAppError):
        UploadDocumentService.upload_for_item(
            request_item, SimpleUploadedFile("x.heic", b"%PDF-1.4 not a photo")
        )
    assert not Document.objects.exists()


@pytest.mark.django_db
def test_supported_formats_on_the_site_include_heic(client):
    page = client.get(reverse("pages:faq")).content.decode()

    assert "HEIC" in page


# --- accepting everything at once ---------------------------------------------------


@pytest.mark.django_db
def test_accept_all(client, user, request_record, request_item):
    second = request_record.items.create(name="Wyciąg")
    third = request_record.items.create(
        name="Raport",
        status=RequestItemStatus.NIE_DOTYCZY,
        not_applicable_reason="Nie mam kasy",
    )
    request_record.items.create(name="Brakujący")
    for item in (request_item, second):
        UploadDocumentService.upload_for_item(item, make_pdf_upload())
    client.force_login(user)

    page = client.get(reverse("requests:detail", args=[request_record.pk]))
    assert "Zaakceptuj wszystkie (3)" in page.content.decode()
    response = client.post(f"/api/requests/{request_record.pk}/accept-all/")

    assert response.json()["data"]["accepted"] == 3
    statuses = dict(request_record.items.values_list("name", "status"))
    assert statuses["Faktury sprzedaży"] == RequestItemStatus.ZAAKCEPTOWANY
    assert statuses["Wyciąg"] == RequestItemStatus.ZAAKCEPTOWANY
    assert statuses["Brakujący"] == RequestItemStatus.BRAK
    third.refresh_from_db()
    assert third.not_applicable_accepted


@pytest.mark.django_db
def test_accept_all_only_in_ones_own_account(client, request_record, request_item):
    from apps.accounts.models import User

    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    stranger = User.objects.create_user(email="obcy@example.com", password="x")
    client.force_login(stranger)

    response = client.post(f"/api/requests/{request_record.pk}/accept-all/")

    assert response.status_code == 404
    request_item.refresh_from_db()
    assert request_item.status == RequestItemStatus.DOSTARCZONY
