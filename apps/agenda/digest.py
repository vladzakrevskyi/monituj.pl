"""The morning "Na dziś" email: on working days at 7:30 (the person's own
clock), for every account they work in - their reminders for today and
overdue ones, deadlines today and tomorrow, requests past their deadline,
questions waiting for an answer longer than a week (with the note of why),
answers to read and what arrived since yesterday. Nothing to say - no email.
Switched off on the calendar page (AgendaSettings.daily_email)."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.urls import reverse
from django.utils import timezone

from apps.accounts import team
from apps.accounts.models import User, is_guest_account
from apps.agenda import calendar
from apps.agenda.models import AgendaSettings, PersonalReminder
from apps.common.site import absolute_url
from apps.demo.models import is_demo_user
from apps.notifications.models import EmailTemplate, Notification
from apps.notifications.services import EmailService
from apps.requests.models import RequestItem, RequestItemKind, RequestItemStatus
from apps.requests.services import in_progress

SEND_AT = time(7, 30)
WAITING_LONG = timedelta(days=7)
LISTED = 5


def _zone(user):
    try:
        return ZoneInfo(user.timezone or "Europe/Warsaw")
    except Exception:
        return ZoneInfo("Europe/Warsaw")


def _section(account, user, today, now):
    reminders = list(
        PersonalReminder.objects.filter(
            account=account, author=user, done_at__isnull=True, due_on__lte=today
        ).select_related("client")
    )
    deadlines = [
        {**event, "day": day}
        for day, event in calendar.deadlines(account, today, today + timedelta(days=1))
    ]
    overdue = in_progress(account).filter(deadline__lt=now).count()
    questions = RequestItem.objects.filter(
        request__created_by=account,
        request__closed_at__isnull=True,
        request__awaiting_confirmation=False,
        kind=RequestItemKind.QUESTION,
    ).select_related("request__client")
    waiting = [
        {
            "client": item.request.client.name,
            "question": item.name,
            "note": item.request.private_note,
            "days": (today - timezone.localtime(item.request.created_at).date()).days,
        }
        for item in questions.filter(
            status__in=[RequestItemStatus.BRAK, RequestItemStatus.ODRZUCONY],
            request__created_at__lt=now - WAITING_LONG,
        ).order_by("request__created_at")
    ]
    to_review = questions.filter(status=RequestItemStatus.DOSTARCZONY).count()
    arrived = Notification.objects.filter(
        user=account, created_at__gte=now - timedelta(days=1)
    ).select_related(
        "document__request_item__request__client", "request_item__request__client"
    )
    arrived_from = sorted({n.item.request.client.name for n in arrived})
    section = {
        "reminders": reminders,
        "deadlines": deadlines,
        "overdue": overdue,
        "waiting": waiting[:LISTED],
        "waiting_count": len(waiting),
        "to_review": to_review,
        "arrived_count": len(arrived),
        "arrived_from": arrived_from[:LISTED],
    }
    section["empty"] = not any(
        [reminders, deadlines, overdue, waiting, to_review, arrived_from]
    )
    return section


def build(user, now=None):
    """-> the sections for each account the person works in, or [] when
    there is nothing to tell."""
    now = now or timezone.now()
    today = timezone.localtime(now, _zone(user)).date()
    accounts = [{"owner": user, "name": "Twoje konto"}]
    for membership in user.memberships.select_related("owner"):
        if team.has_access(membership):
            accounts.append(
                {"owner": membership.owner, "name": team.firm_name(membership.owner)}
            )
    sections = []
    for entry in accounts:
        section = _section(entry["owner"], user, today, now)
        if not section["empty"]:
            sections.append({"name": entry["name"], **section})
    return sections


def due(user, now):
    """Is it this person's 7:30 on a working day, with no email yet today?"""
    local = timezone.localtime(now, _zone(user))
    if local.weekday() >= 5 or local.time() < SEND_AT:
        return None
    settings = AgendaSettings.objects.filter(user=user).first()
    if settings is not None and (
        not settings.daily_email or settings.daily_email_sent_on == local.date()
    ):
        return None
    return local.date()


def send_due(now=None):
    """Called every few minutes by the worker. -> how many emails went out."""
    now = now or timezone.now()
    sent = 0
    people = User.objects.filter(is_active=True, email_verified_at__isnull=False)
    for user in people.iterator():
        if is_demo_user(user) or is_guest_account(user):
            continue
        day = due(user, now)
        if day is None:
            continue
        settings, _ = AgendaSettings.objects.get_or_create(user=user)
        # Marked first: a second worker, or a failure below, sends nothing twice.
        updated = (
            AgendaSettings.objects.filter(pk=settings.pk)
            .exclude(daily_email_sent_on=day)
            .update(daily_email_sent_on=day)
        )
        if not updated:
            continue
        sections = build(user, now)
        if not sections:
            continue
        EmailService.send(
            EmailTemplate.DAILY_AGENDA,
            to_email=user.email,
            context={
                "sections": sections,
                "day": datetime.combine(day, SEND_AT),
                "many_accounts": len(sections) > 1,
                "calendar_link": absolute_url(reverse("agenda:calendar")),
                "questions_link": absolute_url(reverse("requests:questions")),
            },
        )
        sent += 1
    return sent
