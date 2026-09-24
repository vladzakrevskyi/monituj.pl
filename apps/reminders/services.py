from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.common.exceptions import ValidationAppError
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService
from apps.reminders.models import Reminder, ReminderKind
from apps.reminders.schedule import due_dates
from apps.requests.models import Request
from apps.requests.services import RequestStatus, compute_status, with_stats

MANUAL_REMINDER_COOLDOWN = timedelta(seconds=10)


class ReminderService:
    @staticmethod
    def send_manual(request_obj, actor, django_request=None):
        if request_obj.closed_at is not None or request_obj.awaiting_confirmation:
            raise ValidationAppError(
                "Prośba jest zamknięta – otwórz ją ponownie, aby wysłać przypomnienie.",
                code="REQUEST_CLOSED",
            )
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
        if (
            request_obj is None
            or not request_obj.reminders_enabled
            or request_obj.awaiting_confirmation
            or request_obj.closed_at is not None
        ):
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

        sent_times = list(automatic_reminders.values_list("sent_at", flat=True))
        (due_at,) = due_dates(request_obj, sent_times, 1)
        if timezone.now() < due_at:
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


class ReminderScheduleService:
    @staticmethod
    def planned(request_obj, now=None):
        """Upcoming automatic reminders, as local datetimes. Empty when
        reminders are off, the request is complete or the limit is used up."""
        now = now or timezone.now()
        if not request_obj.reminders_enabled:
            return []
        annotated = with_stats(Request.objects.filter(pk=request_obj.pk)).first()
        if compute_status(annotated) in (
            RequestStatus.COMPLETE,
            RequestStatus.CLOSED,
            RequestStatus.AWAITING,
        ):
            return []

        sent_times = list(
            Reminder.objects.filter(request=request_obj, kind=ReminderKind.AUTOMATIC)
            .order_by("sent_at")
            .values_list("sent_at", flat=True)
        )
        remaining = request_obj.max_reminders - len(sent_times)
        if remaining <= 0:
            return []
        # One that is already due goes out within minutes.
        return [
            timezone.localtime(max(due, now))
            for due in due_dates(request_obj, sent_times, remaining)
        ]
