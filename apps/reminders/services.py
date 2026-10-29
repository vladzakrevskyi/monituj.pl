from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.common.exceptions import ValidationAppError
from apps.common.site import absolute_url
from apps.notifications.models import EmailTemplate
from apps.notifications.services import NOT_DELIVERED, EmailService
from apps.reminders.models import Reminder, ReminderKind
from apps.reminders.schedule import (
    DEADLINE_WINDOW,
    RECENT,
    deadline_dates,
    due_dates,
)
from apps.requests.models import Request
from apps.requests.services import (
    RequestStatus,
    check_can_email_others,
    compute_status,
    consume_outbound_email,
    with_stats,
)

# One manual reminder an hour per request is plenty for a person and stops
# the button from being used to flood someone's inbox.
MANUAL_REMINDER_COOLDOWN = timedelta(hours=1)


class ReminderService:
    @staticmethod
    def send_manual(request_obj, actor, django_request=None):
        check_can_email_others(request_obj.created_by)
        if request_obj.closed_at is not None or request_obj.awaiting_confirmation:
            raise ValidationAppError(
                "Prośba jest zamknięta - otwórz ją ponownie, aby wysłać przypomnienie.",
                code="REQUEST_CLOSED",
            )
        annotated = with_stats(Request.objects.filter(pk=request_obj.pk)).first()
        if compute_status(annotated) == RequestStatus.COMPLETE:
            raise ValidationAppError(
                "Wszystkie dokumenty zostały już dostarczone.", code="ALREADY_COMPLETE"
            )

        recent_cutoff = timezone.now() - MANUAL_REMINDER_COOLDOWN
        last = (
            Reminder.objects.filter(request=request_obj, sent_at__gte=recent_cutoff)
            .order_by("-sent_at")
            .first()
        )
        if last is not None:
            next_at = timezone.localtime(last.sent_at + MANUAL_REMINDER_COOLDOWN)
            raise ValidationAppError(
                "Przypomnienie wysłano przed chwilą. Kolejne możesz wysłać od "
                f"{next_at:%H:%M}.",
                code="REMINDER_TOO_SOON",
            )

        consume_outbound_email(request_obj.created_by)
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

    @staticmethod
    def send_combined(requests, actor, django_request=None):
        """One email to a client about all their requests still waiting
        (Zestawienie's "Przypomnij") - not one per request. Each request gets
        its reminder in its history; ones reminded within the hour are left
        out. A single request is the ordinary manual reminder. -> how many
        requests the email was about."""
        if len(requests) == 1:
            ReminderService.send_manual(requests[0], actor, django_request)
            return 1
        owner = requests[0].created_by
        check_can_email_others(owner)
        recent_cutoff = timezone.now() - MANUAL_REMINDER_COOLDOWN
        due = [
            request_obj
            for request_obj in requests
            if request_obj.closed_at is None
            and not request_obj.awaiting_confirmation
            and not Reminder.objects.filter(
                request=request_obj, sent_at__gte=recent_cutoff
            ).exists()
        ]
        if not due:
            raise ValidationAppError(
                "Przypomnienie wysłano przed chwilą.", code="REMINDER_TOO_SOON"
            )
        if len(due) == 1:
            ReminderService.send_manual(due[0], actor, django_request)
            return 1
        consume_outbound_email(owner)
        for request_obj in due:
            Reminder.objects.create(
                request=request_obj,
                kind=ReminderKind.MANUAL,
                sequence_number=Reminder.objects.filter(request=request_obj).count()
                + 1,
                triggered_by=actor,
            )
            AuditService.log(
                AuditEvent.REMINDER_SENT,
                actor=actor,
                target=request_obj,
                request=django_request,
                metadata={"combined": True},
            )
        EmailService.send(
            EmailTemplate.REMINDER_COMBINED,
            to_email=due[0].client.email,
            context={
                "requests": [
                    {
                        "name": request_obj.name,
                        "deadline": request_obj.deadline,
                        "missing_items": list(
                            request_obj.items.filter(status__in=NOT_DELIVERED)
                            .order_by("id")
                            .values_list("name", flat=True)
                        ),
                        "link": absolute_url(f"/d/{request_obj.public_token}/"),
                    }
                    for request_obj in sorted(
                        due, key=lambda r: (r.deadline is None, r.deadline or 0)
                    )
                ],
            },
            request=due[0],
        )
        return len(due)


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

        count = Reminder.objects.filter(
            request=request_obj, kind=ReminderKind.AUTOMATIC
        ).count()
        if count >= request_obj.max_reminders:
            return False

        (due_at,) = due_dates(request_obj, _interval_anchor(request_obj), 1)
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


def _interval_anchor(request_obj):
    """The reminders the next interval one counts from: automatic ones and
    those before the deadline - so a deadline reminder isn't followed by
    another the same day."""
    return list(
        Reminder.objects.filter(
            request=request_obj,
            kind__in=[ReminderKind.AUTOMATIC, ReminderKind.DEADLINE],
        )
        .order_by("sent_at")
        .values_list("sent_at", flat=True)
    )


class DeadlineReminderService:
    """Two days before the deadline and on its day - when documents are
    still missing and reminders are on (apps/reminders/schedule.py)."""

    @staticmethod
    @transaction.atomic
    def maybe_send_for_request(request_id, now=None):
        now = now or timezone.now()
        request_obj = Request.objects.select_for_update().filter(pk=request_id).first()
        if (
            request_obj is None
            or request_obj.deadline is None
            or not request_obj.reminders_enabled
            or request_obj.awaiting_confirmation
            or request_obj.closed_at is not None
        ):
            return False
        annotated = with_stats(Request.objects.filter(pk=request_id)).first()
        if compute_status(annotated) == RequestStatus.COMPLETE:
            return False

        sent = set(
            Reminder.objects.filter(
                request=request_obj, kind=ReminderKind.DEADLINE
            ).values_list("sequence_number", flat=True)
        )
        for sequence, due in deadline_dates(request_obj):
            if sequence in sent or now < due:
                continue
            if now >= min(due + DEADLINE_WINDOW, request_obj.deadline):
                continue  # missed - the next one is closer
            # Not right after another reminder, or the request itself.
            recent = (
                Reminder.objects.filter(
                    request=request_obj, sent_at__gte=due - RECENT
                ).exists()
                or request_obj.created_at >= due - RECENT
            )
            if recent:
                continue
            Reminder.objects.create(
                request=request_obj,
                kind=ReminderKind.DEADLINE,
                sequence_number=sequence,
            )
            AuditService.log(AuditEvent.REMINDER_SENT, target=request_obj)
            days_left = (
                timezone.localtime(request_obj.deadline, due.tzinfo).date() - due.date()
            ).days
            EmailService.send(
                EmailTemplate.REMINDER,
                to_email=request_obj.client.email,
                context={"request_name": request_obj.name, "days_left": days_left},
                request=request_obj,
            )
            return True
        return False


class ReminderScheduleService:
    @staticmethod
    def planned(request_obj, now=None):
        """Upcoming reminders as the senders above will send them -
        [{"at": local datetime, "kind": "automatic" | "before_deadline" |
        "deadline_day" | "after_deadline"}]. A deadline reminder goes first
        and the next interval one counts from it; one too soon after another
        reminder is not sent at all. Empty when reminders are off, the
        request is complete or the limit is used up."""
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

        sent = Reminder.objects.filter(request=request_obj)
        anchors = _interval_anchor(request_obj)
        automatic_left = (
            request_obj.max_reminders - sent.filter(kind=ReminderKind.AUTOMATIC).count()
        )
        sent_deadline = set(
            sent.filter(kind=ReminderKind.DEADLINE).values_list(
                "sequence_number", flat=True
            )
        )
        pending = [
            (sequence, due)
            for sequence, due in deadline_dates(request_obj)
            if sequence not in sent_deadline
        ]
        last = sent.order_by("-sent_at").values_list("sent_at", flat=True).first()
        last = max(filter(None, [last, request_obj.created_at]))

        planned = []
        while True:
            pending = [
                (sequence, due)
                for sequence, due in pending
                if max(due, now) < min(due + DEADLINE_WINDOW, request_obj.deadline)
            ]
            automatic = (
                max(due_dates(request_obj, anchors, 1)[0], now)
                if automatic_left > 0
                else None
            )
            if pending and (automatic is None or max(pending[0][1], now) <= automatic):
                sequence, due = pending.pop(0)
                if last >= due - RECENT:
                    continue  # right after another one: skipped
                when = max(due, now)
                kind = "before_deadline" if sequence == 1 else "deadline_day"
            elif automatic is not None:
                when, automatic_left = automatic, automatic_left - 1
                past = request_obj.deadline and when > request_obj.deadline
                kind = "after_deadline" if past else "automatic"
            else:
                break
            planned.append({"at": timezone.localtime(when), "kind": kind})
            anchors.append(when)
            last = when
        return planned
