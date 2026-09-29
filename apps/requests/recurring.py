"""Recurring requests: the same request to the same clients again and again
- every day, every week, every two weeks or every month.

The calendar is taken seriously:
- monthly on the 29th-31st means the month's last day when the month is
  shorter ("ostatni dzień miesiąca" is simply the 31st);
- every two weeks keeps its rhythm from the first sending day;
- "codziennie" means working days only (no weekends, no Polish public
  holidays) unless the owner wants every day; for the other intervals a day
  off moves the sending to the next working day, without shifting the
  schedule itself.

A schedule goes out on its day from 8:00 in the owner's time zone (the task
send_recurring_requests, every 15 minutes) as ordinary requests created by
RequestService.create_many - to all of its clients or none, within the
plan's free places. At most once per period (day, week, two weeks, month),
and days missed while the server was down are not caught up. "Wyślij teraz"
is an extra send on top: the schedule stays as it was. A run that can't go out is skipped until
the next period, and the owner gets an email saying why."""

import logging
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from apps.common.exceptions import ApplicationError, NotFoundAppError
from apps.common.site import absolute_url
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService
from apps.requests.models import (
    LAST_DAY_OF_MONTH,
    RecurringInterval,
    RecurringRequest,
)
from apps.requests.services import RequestService

logger = logging.getLogger("monituj")

SEND_HOUR = 8
MONTH_TOKENS = ("{miesiąc}", "{miesiac}")
DATE_TOKEN = "{data}"
# "w poniedziałek", "we wtorek", "w środę"... - 0 is Monday.
WEEKDAYS_ON = [
    "w poniedziałek",
    "we wtorek",
    "w środę",
    "w czwartek",
    "w piątek",
    "w sobotę",
    "w niedzielę",
]


# --- the Polish calendar ------------------------------------------------------


def _easter(year):
    """Easter Sunday (the Gregorian computus)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


@lru_cache(maxsize=32)
def holidays(year):
    """Polish public holidays (days off work) of the year."""
    easter = _easter(year)
    days = {
        date(year, 1, 1),  # Nowy Rok
        date(year, 1, 6),  # Trzech Króli
        easter,
        easter + timedelta(days=1),  # Poniedziałek Wielkanocny
        date(year, 5, 1),
        date(year, 5, 3),
        easter + timedelta(days=49),  # Zielone Świątki
        easter + timedelta(days=60),  # Boże Ciało
        date(year, 8, 15),
        date(year, 11, 1),
        date(year, 11, 11),
        date(year, 12, 25),
        date(year, 12, 26),
    }
    if year >= 2025:
        days.add(date(year, 12, 24))  # Wigilia - a day off since 2025
    return frozenset(days)


def is_working_day(day):
    return day.weekday() < 5 and day not in holidays(day.year)


def next_working_day(day):
    while not is_working_day(day):
        day += timedelta(days=1)
    return day


# --- the schedule ---------------------------------------------------------------


def _month_day(year, month, wanted):
    """The wanted day in that month - its last day when the month is shorter."""
    first_of_next = (date(year, month, 1) + timedelta(days=32)).replace(day=1)
    last = (first_of_next - timedelta(days=1)).day
    return date(year, month, min(wanted, last))


def _next_month_start(day):
    return (day.replace(day=1) + timedelta(days=32)).replace(day=1)


def _weekday_on_or_after(day, weekday):
    return day + timedelta(days=(weekday - day.weekday()) % 7)


def due_on_or_after(schedule, day):
    """The first day of the schedule on or after `day` - before a day off
    moves it (sending_day)."""
    interval = schedule.interval
    if interval == RecurringInterval.DAILY:
        return next_working_day(day) if schedule.workdays_only else day
    if interval == RecurringInterval.WEEKLY:
        return _weekday_on_or_after(day, schedule.weekday)
    if interval == RecurringInterval.BIWEEKLY:
        anchor = schedule.anchor_on
        if day <= anchor:
            return anchor
        return anchor + timedelta(days=-((anchor - day).days // 14) * 14)
    candidate = _month_day(day.year, day.month, schedule.month_day)
    if candidate < day:
        start = _next_month_start(day)
        candidate = _month_day(start.year, start.month, schedule.month_day)
    return candidate


def next_period_start(schedule, day):
    """The first day of the period after the one `day` is in."""
    interval = schedule.interval
    if interval == RecurringInterval.DAILY:
        return day + timedelta(days=1)
    if interval == RecurringInterval.WEEKLY:
        return day + timedelta(days=7 - day.weekday())
    if interval == RecurringInterval.BIWEEKLY:
        anchor = schedule.anchor_on
        if day < anchor:
            return anchor
        return anchor + timedelta(days=((day - anchor).days // 14 + 1) * 14)
    return _next_month_start(day)


def sending_day(schedule, due):
    """The day a due date actually goes out: a day off moves it to the next
    working day (daily schedules only ever fall on their own days)."""
    if schedule.interval != RecurringInterval.DAILY and schedule.workdays_only:
        return next_working_day(due)
    return due


def _set_next(schedule, due):
    schedule.next_due_on = due
    schedule.next_run_on = sending_day(schedule, due)


def _advance(schedule, after, today):
    """The next period's day after `after` - never one already gone: days
    missed are not caught up."""
    due = due_on_or_after(schedule, next_period_start(schedule, after))
    while sending_day(schedule, due) <= today:
        due = due_on_or_after(schedule, next_period_start(schedule, due))
    _set_next(schedule, due)


def start(schedule, today, send_now):
    """Sets the first automatic run: the first day of the schedule from
    today on - or, when the first requests go out now, from the next
    period on."""
    if schedule.interval == RecurringInterval.BIWEEKLY:
        # The rhythm starts on the chosen weekday - a week later when the
        # first requests went out today, so the next ones aren't days away.
        base = today + timedelta(days=7) if send_now else today
        schedule.anchor_on = _weekday_on_or_after(base, schedule.weekday)
        _set_next(schedule, schedule.anchor_on)
        return
    first = next_period_start(schedule, today) if send_now else today
    _set_next(schedule, due_on_or_after(schedule, first))


def upcoming(schedule, count=3):
    """The next sending days, for the screens."""
    days, due = [], schedule.next_due_on
    for _ in range(count):
        days.append(sending_day(schedule, due))
        due = due_on_or_after(schedule, next_period_start(schedule, due))
    return days


def describe(schedule):
    """ "co miesiąc, ostatniego dnia", "co 2 tygodnie w piątek"..."""
    interval = schedule.interval
    if interval == RecurringInterval.DAILY:
        return "codziennie w dni robocze" if schedule.workdays_only else "codziennie"
    if interval == RecurringInterval.WEEKLY:
        return f"co tydzień {WEEKDAYS_ON[schedule.weekday]}"
    if interval == RecurringInterval.BIWEEKLY:
        return f"co 2 tygodnie {WEEKDAYS_ON[schedule.weekday]}"
    if schedule.month_day >= LAST_DAY_OF_MONTH:
        return "co miesiąc, ostatniego dnia"
    return f"co miesiąc, {schedule.month_day}. dnia"


# --- names ------------------------------------------------------------------------


def month_label(day):
    """The month the documents are for: the one before the sending day."""
    previous = day.replace(day=1) - timedelta(days=1)
    # "za wrzesień 2026" - Polish month names are lower case mid-sentence.
    return f"{date_format(previous, 'F').lower()} {previous.year}"


def render_name(template, day):
    name = template
    for token in MONTH_TOKENS:
        name = name.replace(token, month_label(day))
    return name.replace(DATE_TOKEN, day.strftime("%d.%m.%Y"))


# --- running ------------------------------------------------------------------------


def owner_now(owner):
    try:
        zone = ZoneInfo(owner.timezone or "Europe/Warsaw")
    except ZoneInfoNotFoundError, ValueError:
        zone = ZoneInfo("Europe/Warsaw")
    return timezone.now().astimezone(zone)


def next_month_day(after, wanted):
    """The next `wanted` day of a month after `after` (its last day in a
    shorter month)."""
    candidate = _month_day(after.year, after.month, wanted)
    if candidate <= after:
        start = _next_month_start(after)
        candidate = _month_day(start.year, start.month, wanted)
    return candidate


def _deadline(schedule, day):
    if schedule.deadline_month_day:
        last = next_month_day(day, schedule.deadline_month_day)
    elif schedule.deadline_days:
        last = day + timedelta(days=schedule.deadline_days)
    else:
        return None
    return timezone.make_aware(datetime.combine(last, time.max))


def describe_deadline(schedule):
    if schedule.deadline_month_day:
        return f"termin: do {schedule.deadline_month_day}. dnia miesiąca"
    if schedule.deadline_days:
        return f"termin: {schedule.deadline_days} dni"
    return "bez terminu"


def _move_on(schedule, today, manual):
    if not manual:
        _advance(schedule, schedule.next_due_on, today)
    elif next_period_start(schedule, today) > schedule.next_due_on:
        # By hand: stands for today's period - unless the next run is
        # already in a later one.
        _advance(schedule, today, today)


def run(schedule, today, request=None, manual=False, extra=False):
    """Sends the requests of the current period and moves the schedule on.
    Returns them; raises ApplicationError when they can't go out - nothing
    is sent then, and the caller decides what to keep. `extra`: sent by hand
    on top of the schedule, which stays exactly as it was."""
    client_ids = list(
        schedule.clients.filter(owner=schedule.owner).values_list("pk", flat=True)
    )
    if not extra:
        schedule.last_run_at = timezone.now()
        _move_on(schedule, today, manual)
    if not client_ids:
        raise ApplicationError("W tej prośbie cyklicznej nie ma już klientów.")
    sent = RequestService.create_many(
        owner=schedule.owner,
        client_ids=client_ids,
        name=render_name(schedule.name, today),
        description=schedule.description,
        deadline=_deadline(schedule, today),
        item_names=schedule.item_names,
        reminder_settings={
            "reminders_enabled": schedule.reminders_enabled,
            "first_reminder_after_days": schedule.first_reminder_after_days,
            "reminder_frequency_days": schedule.reminder_frequency_days,
            "max_reminders": schedule.max_reminders,
            "retention_days": schedule.retention_days,
        },
        request=request,
        recurring=schedule,
    )
    if not extra:
        schedule.last_result = {"sent": len(sent)}
        schedule.save()
    return sent


def run_due(now=None):
    """Sends every schedule whose day has come (from 8:00, owner's time).
    Returns how many schedules ran."""
    ran = 0
    horizon = (now or timezone.now()).date() + timedelta(days=1)
    for pk in (
        RecurringRequest.objects.filter(active=True, next_run_on__lte=horizon)
        .order_by("next_run_on")
        .values_list("pk", flat=True)
    ):
        with transaction.atomic():
            schedule = (
                RecurringRequest.objects.select_for_update(skip_locked=True)
                .select_related("owner")
                .filter(pk=pk, active=True)
                .first()
            )
            if schedule is None:
                continue
            local = owner_now(schedule.owner) if now is None else now
            today = local.date()
            if schedule.next_run_on > today or (
                schedule.next_run_on == today and local.hour < SEND_HOUR
            ):
                continue
            due = schedule.next_due_on
            try:
                # Its own savepoint: a refused run leaves the schedule moved on.
                with transaction.atomic():
                    run(schedule, today)
            except ApplicationError as exc:
                schedule.last_run_at = timezone.now()
                schedule.next_due_on = due
                _move_on(schedule, today, manual=False)
                schedule.last_result = {"skipped": exc.message}
                schedule.save()
                _tell_owner_skipped(schedule, today, exc.message)
            ran += 1
    return ran


def _tell_owner_skipped(schedule, today, reason):
    EmailService.send(
        EmailTemplate.RECURRING_SKIPPED,
        to_email=schedule.owner.email,
        context={
            "request_name": render_name(schedule.name, today),
            "reason": reason,
            "clients_count": schedule.clients.count(),
            "next_run_on": schedule.next_run_on,
            "list_url": absolute_url(reverse("requests:list")),
        },
    )


def create(
    owner,
    client_ids,
    name,
    description,
    item_names,
    timing,
    deadline_days,
    settings,
    send_now,
    new_clients=(),
    request=None,
    deadline_month_day=None,
):
    """Saves a schedule - and with send_now also sends the current period's
    requests at once. All or nothing: if they can't go out (no free places
    in the plan), nothing is saved, new clients included. `timing`:
    interval, month_day, weekday, workdays_only. Returns (schedule, requests
    sent now)."""
    from apps.clients.models import Client
    from apps.clients.services import ClientService

    with transaction.atomic():
        ids = list(client_ids)
        for client_name, email in new_clients:
            ids.append(
                ClientService.get_or_create_by_email(
                    owner=owner, email=email, name=client_name, request=request
                ).pk
            )
        ids = list(dict.fromkeys(ids))
        if Client.objects.filter(owner=owner, pk__in=ids).count() != len(ids):
            raise NotFoundAppError("Nie znaleziono klienta.")
        today = owner_now(owner).date()
        schedule = RecurringRequest(
            owner=owner,
            name=name,
            description=description,
            item_names=item_names,
            deadline_days=deadline_days,
            deadline_month_day=deadline_month_day,
            **timing,
            **settings,
        )
        start(schedule, today, send_now)
        schedule.save()
        schedule.clients.set(ids)
        sent = []
        if send_now:
            # This period's requests; the schedule already starts with the
            # next period, so the run doesn't move it.
            sent = run(schedule, today, request=request, manual=True)
    return schedule, sent


def reschedule(schedule, today):
    """After the timing was edited: the next day of the new schedule - from
    the next period on if the current one already went out."""
    last = None
    if schedule.last_run_at is not None:
        last = schedule.last_run_at.astimezone(owner_now(schedule.owner).tzinfo)
        last = last.date()
    if schedule.interval == RecurringInterval.BIWEEKLY:
        recently = last is not None and (today - last).days < 14
    else:
        recently = last is not None and next_period_start(schedule, last) > today
    start(schedule, today, send_now=recently)
