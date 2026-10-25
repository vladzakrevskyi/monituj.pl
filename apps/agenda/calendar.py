"""What the calendar shows, for one account (the workspace) and one month:

- deadlines of requests still missing documents, and of questions still
  waiting for an answer;
- the days recurring requests go out;
- the team's own reminders ("Przypomnij mi").

Monituj's automatic reminders to clients aren't drawn - they go out by
themselves and stop by themselves.
"""

import calendar as pycalendar
from datetime import date, timedelta

from django.urls import reverse
from django.utils import timezone

from apps.agenda.models import PersonalReminder
from apps.requests import recurring
from apps.requests.models import (
    RecurringRequest,
    RequestItem,
    RequestItemKind,
    RequestItemStatus,
)
from apps.requests.services import in_progress

MONTHS = [
    "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
    "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień",
]  # fmt: skip
WEEKDAYS_SHORT = ["PON", "WT", "ŚR", "CZW", "PT", "SOB", "NIEDZ"]
# Upcoming sending days asked of a recurring request - enough for a month
# of a daily one.
SENDS_LOOKED_AT = 40


def month_bounds(year, month):
    first = date(year, month, 1)
    last = date(year, month, pycalendar.monthrange(year, month)[1])
    return first, last


def weeks(year, month):
    """The month's grid, Monday first: [[date x 7], ...]."""
    first, last = month_bounds(year, month)
    start = first - timedelta(days=first.weekday())
    end = last + timedelta(days=6 - last.weekday())
    days = [start + timedelta(days=n) for n in range((end - start).days + 1)]
    return [days[i : i + 7] for i in range(0, len(days), 7)]


def _local_day(moment):
    return timezone.localtime(moment).date()


def deadlines(account, start, end):
    """[(day, event)] - requests and questions due in [start, end]."""
    found = []
    for request_obj in (
        in_progress(account)
        .filter(deadline__isnull=False)
        .select_related("client")
        .order_by("deadline")
    ):
        day = _local_day(request_obj.deadline)
        if start <= day <= end:
            found.append(
                (
                    day,
                    {
                        "kind": "deadline",
                        "label": f"Termin: {request_obj.name}",
                        "client": request_obj.client.name,
                        "url": reverse("requests:detail", args=[request_obj.pk]),
                    },
                )
            )
    questions = RequestItem.objects.filter(
        request__created_by=account,
        request__closed_at__isnull=True,
        request__deadline__isnull=False,
        kind=RequestItemKind.QUESTION,
        status__in=[RequestItemStatus.BRAK, RequestItemStatus.ODRZUCONY],
    ).select_related("request__client")
    for item in questions:
        day = _local_day(item.request.deadline)
        if start <= day <= end:
            found.append(
                (
                    day,
                    {
                        "kind": "question",
                        "label": f"Pytanie: {item.name}",
                        "client": item.request.client.name,
                        "url": reverse("requests:detail", args=[item.request_id]),
                    },
                )
            )
    return found


def sends(account, start, end):
    """[(day, event)] - recurring requests going out in [start, end]."""
    found = []
    for schedule in RecurringRequest.objects.filter(owner=account, active=True):
        clients = schedule.clients.count()
        for day in recurring.upcoming(schedule, count=SENDS_LOOKED_AT):
            if day > end:
                break
            if day >= start:
                found.append(
                    (
                        day,
                        {
                            "kind": "send",
                            "label": f"Wysyłka: {schedule.name}",
                            "client": f"{clients} klientów"
                            if clients != 1
                            else "1 klient",
                            "url": reverse(
                                "requests:recurring-edit", args=[schedule.pk]
                            ),
                        },
                    )
                )
    return found


def reminders(account, start, end):
    """[(day, event)] - the team's own reminders in [start, end]."""
    found = []
    for reminder in PersonalReminder.objects.filter(
        account=account, due_on__range=(start, end)
    ).select_related("client", "author"):
        found.append(
            (
                reminder.due_on,
                {
                    "kind": "mine",
                    "label": reminder.text,
                    "client": reminder.client.name if reminder.client else "",
                    "url": (
                        reverse("clients:detail", args=[reminder.client_id])
                        if reminder.client_id
                        else ""
                    ),
                    "done": reminder.is_done,
                    "reminder": reminder,
                },
            )
        )
    return found


def month(account, year, month_number):
    """{"weeks": [[{"day", "in_month", "today", "events"}]], "title", ...}."""
    grid = weeks(year, month_number)
    start, end = grid[0][0], grid[-1][-1]
    by_day = {}
    for day, event in [
        *reminders(account, start, end),
        *deadlines(account, start, end),
        *sends(account, start, end),
    ]:
        by_day.setdefault(day, []).append(event)
    today = timezone.localdate()
    first, _last = month_bounds(year, month_number)
    previous = first - timedelta(days=1)
    following = first + timedelta(days=32)
    return {
        "title": f"{MONTHS[month_number - 1]} {year}",
        "weekdays": WEEKDAYS_SHORT,
        "weeks": [
            [
                {
                    "day": day,
                    "in_month": day.month == month_number,
                    "today": day == today,
                    "weekend": day.weekday() >= 5,
                    "events": by_day.get(day, []),
                }
                for day in week
            ]
            for week in grid
        ],
        "previous": f"{previous.year}-{previous.month:02d}",
        "next": f"{following.year}-{following.month:02d}",
        "is_current": (year, month_number) == (today.year, today.month),
    }


def today_summary(account, user):
    """The panel beside the calendar - and the morning email's base."""
    today = timezone.localdate()
    open_reminders = PersonalReminder.objects.filter(
        account=account, done_at__isnull=True, due_on__lte=today
    ).select_related("client", "author")
    waiting = RequestItem.objects.filter(
        request__created_by=account,
        request__closed_at__isnull=True,
        request__awaiting_confirmation=False,
        kind=RequestItemKind.QUESTION,
        status__in=[RequestItemStatus.BRAK, RequestItemStatus.ODRZUCONY],
        request__created_at__lt=timezone.now() - timedelta(days=7),
    )
    to_review = RequestItem.objects.filter(
        request__created_by=account,
        request__closed_at__isnull=True,
        kind=RequestItemKind.QUESTION,
        status=RequestItemStatus.DOSTARCZONY,
    )
    due_today = [event for day, event in deadlines(account, today, today)]
    return {
        "today": today,
        "reminders": list(open_reminders),
        "waiting_long": waiting.count(),
        "to_review": to_review.count(),
        "due_today": due_today,
    }
