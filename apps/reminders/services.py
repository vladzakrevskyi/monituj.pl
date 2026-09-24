from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.common.exceptions import ValidationAppError
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService
from apps.reminders.models import Reminder, ReminderKind
from apps.requests.models import Request
from apps.requests.services import RequestStatus, compute_status, with_stats

MANUAL_REMINDER_COOLDOWN = timedelta(seconds=10)


class ReminderService:
    @staticmethod
    def send_manual(request_obj, actor, django_request=None):
        annotated = with_stats(Request.objects.filter(pk=request_obj.pk)).first()
        if compute_status(annotated) == RequestStatus.COMPLETE:
            raise ValidationAppError(
                "Wszystkie dokumenty zostały już dostarczone.", code="ALREADY_COMPLETE"
            )

        recent_cutoff = timezone.now() - MANUAL_REMINDER_COOLDOWN
        if Reminder.objects.filter(
            request=request_obj, sent_at__gte=recent_cutoff
        ).exists():
            raise ValidationAppError(
                "Przypomnienie zostało już wysłane. Spróbuj ponownie za chwilę.",
                code="REMINDER_TOO_SOON",
            )

        sequence_number = Reminder.objects.filter(request=request_obj).count() + 1
        reminder = Reminder.objects.create(
            request=request_obj,
            kind=ReminderKind.MANUAL,
            sequence_number=sequence_number,
            triggered_by=actor,
        )
        AuditService.log(
            AuditEvent.REMINDER_SENT,
            actor=actor,
            target=request_obj,
            request=django_request,
        )
        EmailService.send(
            EmailTemplate.REMINDER,
            to_email=request_obj.client.email,
            context={"request_name": request_obj.name},
            request=request_obj,
        )
        return reminder


class AutomaticReminderService:
    @staticmethod
    @transaction.atomic
    def maybe_send_for_request(request_id):
        request_obj = Request.objects.select_for_update().filter(pk=request_id).first()
        if request_obj is None or not request_obj.reminders_enabled:
            return False

        annotated = with_stats(Request.objects.filter(pk=request_id)).first()
        if compute_status(annotated) == RequestStatus.COMPLETE:
            return False

        automatic_reminders = Reminder.objects.filter(
            request=request_obj, kind=ReminderKind.AUTOMATIC
        ).order_by("sent_at")
        count = automatic_reminders.count()
        if count >= request_obj.max_reminders:
            return False

        now = timezone.now()
        if count == 0:
            due_at = request_obj.created_at + timedelta(
                days=request_obj.first_reminder_after_days
            )
        else:
            last_sent = automatic_reminders.last().sent_at
            due_at = last_sent + timedelta(days=request_obj.reminder_frequency_days)

        if now < due_at:
            return False
        if timezone.localtime(now).hour < request_obj.reminder_send_hour:
            return False

        Reminder.objects.create(
            request=request_obj,
            kind=ReminderKind.AUTOMATIC,
            sequence_number=count + 1,
        )
        AuditService.log(AuditEvent.REMINDER_SENT, target=request_obj)
        EmailService.send(
            EmailTemplate.REMINDER,
            to_email=request_obj.client.email,
            context={"request_name": request_obj.name},
            request=request_obj,
        )
        return True


def _next_send_time(due_at, send_hour, now):
    """The hourly task sends at its first run on or after due_at once the
    local hour has reached send_hour; mirror that to predict the send time."""
    candidate = timezone.localtime(max(due_at, now))
    if candidate.hour < send_hour:
        return candidate.replace(hour=send_hour, minute=0, second=0, microsecond=0)
    if candidate.minute or candidate.second or candidate.microsecond:
        candidate = candidate.replace(minute=0, second=0, microsecond=0) + timedelta(
            hours=1
        )
    return candidate


class ReminderScheduleService:
    @staticmethod
    def planned(request_obj, now=None):
        """Upcoming automatic reminders, as local datetimes. Empty when
        reminders are off, the request is complete or the limit is used up."""
        now = now or timezone.now()
        if not request_obj.reminders_enabled:
            return []
        annotated = with_stats(Request.objects.filter(pk=request_obj.pk)).first()
        if compute_status(annotated) == RequestStatus.COMPLETE:
            return []

        sent = list(
            Reminder.objects.filter(
                request=request_obj, kind=ReminderKind.AUTOMATIC
            ).order_by("sent_at")
        )
        remaining = request_obj.max_reminders - len(sent)
        if remaining <= 0:
            return []

        if sent:
            due_at = sent[-1].sent_at + timedelta(
                days=request_obj.reminder_frequency_days
            )
        else:
            due_at = request_obj.created_at + timedelta(
                days=request_obj.first_reminder_after_days
            )

        planned = []
        for _ in range(remaining):
            send_at = _next_send_time(due_at, request_obj.reminder_send_hour, now)
            planned.append(send_at)
            due_at = send_at + timedelta(days=request_obj.reminder_frequency_days)
        return planned
