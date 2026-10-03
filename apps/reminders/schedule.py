"""When automatic reminders go out.

A reminder is sent at the clock time the request itself was sent, in the
sender's zone - e.g. 14:20 - but on the recipient's clock: a request sent at
14:20 in Warsaw reminds a recipient in New York at 14:20 New York time. Times
outside 8:00-20:00 are moved into that window, so nobody gets a reminder at
night. When the recipient's zone is unknown, the sender's is used.

With a deadline, two more reminders: DEADLINE_DAYS_BEFORE days before it and
on its day, at the same clock time (deadline_dates). They are skipped when
another reminder went out shortly before (RECENT), and the interval
reminders count from the latest reminder of either kind, so the two never
land on the same day."""

from datetime import datetime, time, timedelta

from django.utils import timezone

from apps.accounts.models import User
from apps.common.timezones import valid_timezone, zone
from apps.requests.models import RecipientAccess

WINDOW_START = time(8, 0)
WINDOW_END = time(20, 0)


def send_clock(request_obj):
    sent = timezone.localtime(request_obj.created_at, zone(request_obj.sender_timezone))
    clock = time(sent.hour, sent.minute)
    return min(max(clock, WINDOW_START), WINDOW_END)


def recipient_zone(request_obj):
    email = request_obj.client.email
    access = RecipientAccess.objects.filter(email__iexact=email).first()
    if access and valid_timezone(access.timezone):
        return zone(access.timezone)
    user = User.objects.filter(email__iexact=email, is_active=True).first()
    if user and valid_timezone(user.timezone):
        return zone(user.timezone)
    return zone(request_obj.sender_timezone)


def _at_clock(base, days, clock, recipient_tz):
    day = timezone.localtime(base, recipient_tz).date() + timedelta(days=days)
    return datetime.combine(day, clock, tzinfo=recipient_tz)


def due_dates(request_obj, sent_times, count):
    """The next `count` reminder times, given the automatic reminders
    already sent (oldest first): the first one a few days after the request,
    each following one a few days after the previous."""
    clock = send_clock(request_obj)
    recipient_tz = recipient_zone(request_obj)
    if sent_times:
        due = _at_clock(
            sent_times[-1], request_obj.reminder_frequency_days, clock, recipient_tz
        )
    else:
        due = _at_clock(
            request_obj.created_at,
            request_obj.first_reminder_after_days,
            clock,
            recipient_tz,
        )
    dates = []
    for _ in range(count):
        dates.append(due)
        due = _at_clock(due, request_obj.reminder_frequency_days, clock, recipient_tz)
    return dates


DEADLINE_DAYS_BEFORE = 2
# A deadline reminder isn't sent this soon after another reminder (or the
# request itself).
RECENT = timedelta(hours=20)
# How long after its time a deadline reminder may still go out - the task
# runs every few minutes; later it would be a different day's message.
DEADLINE_WINDOW = timedelta(hours=12)


def deadline_dates(request_obj):
    """[(sequence, due)] - the reminder DEADLINE_DAYS_BEFORE days before the
    deadline (1) and on its day (2), at the request's clock, on the
    recipient's calendar. Empty without a deadline."""
    if request_obj.deadline is None:
        return []
    clock = send_clock(request_obj)
    recipient_tz = recipient_zone(request_obj)
    day = timezone.localtime(request_obj.deadline, recipient_tz).date()
    return [
        (sequence, datetime.combine(day - timedelta(days=before), clock, recipient_tz))
        for sequence, before in ((1, DEADLINE_DAYS_BEFORE), (2, 0))
    ]
