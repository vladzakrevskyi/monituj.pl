"""The office's own memory (apps/agenda): reminders for oneself, the calendar
with deadlines and recurring sends, the calendar feed for a phone and the
morning "Na dziś" email."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.agenda import calendar, digest, ics
from apps.agenda.models import AgendaSettings, PersonalReminder, settings_for
from apps.requests import questions
from tests.conftest import page_text

WARSAW = ZoneInfo("Europe/Warsaw")


def _plain(text):
    return text.replace(" ", " ")


def _at(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), tzinfo=WARSAW)


@pytest.fixture(autouse=True)
def _verified(request):
    """The morning email goes to confirmed addresses only."""
    if "user" in request.fixturenames:
        found = request.getfixturevalue("user")
        found.email_verified_at = timezone.now()
        found.save(update_fields=["email_verified_at"])


def _monday():
    today = timezone.localdate()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


# --- reminders and the calendar ---------------------------------------------------


@pytest.mark.django_db
def test_reminder_is_added_shown_and_ticked_off(client, user, client_record):
    client.force_login(user)
    day = timezone.localdate()

    client.post(
        reverse("agenda:reminder-add"),
        {
            "text": "Zadzwonić do Kowalskiego",
            "due_on": day.isoformat(),
            "client": client_record.pk,
        },
    )

    reminder = PersonalReminder.objects.get()
    assert reminder.account == user and reminder.author == user
    page = _plain(page_text(client.get(reverse("agenda:calendar"))))
    assert page.count("Zadzwonić do Kowalskiego") >= 2  # the grid and "Dziś"
    card = _plain(
        page_text(client.get(reverse("clients:detail", args=[client_record.pk])))
    )
    assert "Zadzwonić do Kowalskiego" in card

    client.post(reverse("agenda:reminder-done", args=[reminder.pk]))
    reminder.refresh_from_db()
    assert reminder.is_done


@pytest.mark.django_db
def test_reminder_from_the_card_goes_back_to_the_card(client, user, client_record):
    client.force_login(user)
    card = reverse("clients:detail", args=[client_record.pk])

    response = client.post(
        reverse("agenda:reminder-add"),
        {
            "text": "Umowa leasingu",
            "due_on": (timezone.localdate() + timedelta(days=1)).isoformat(),
            "client": client_record.pk,
            "next": card,
        },
    )

    assert response["Location"] == card
    response = client.post(
        reverse("agenda:reminder-add"),
        {
            "text": "x",
            "due_on": timezone.localdate().isoformat(),
            "next": "https://evil.example/",
        },
    )
    assert response["Location"] == reverse("agenda:calendar")


@pytest.mark.django_db
def test_reminder_needs_text_and_day(client, user):
    client.force_login(user)

    client.post(reverse("agenda:reminder-add"), {"text": "", "due_on": ""})

    assert not PersonalReminder.objects.exists()


@pytest.mark.django_db
def test_others_reminders_cannot_be_touched(client, user):
    from apps.accounts.models import User

    reminder = PersonalReminder.objects.create(
        account=user,
        author=user,
        text="Tajne-przypomnienie",
        due_on=timezone.localdate(),
    )
    stranger = User.objects.create_user(email="obcy@example.com", password="x")
    client.force_login(stranger)

    assert (
        client.post(reverse("agenda:reminder-done", args=[reminder.pk])).status_code
        == 404
    )
    assert (
        client.post(reverse("agenda:reminder-delete", args=[reminder.pk])).status_code
        == 404
    )
    assert PersonalReminder.objects.filter(done_at__isnull=True).count() == 1
    assert "Tajne-przypomnienie" not in page_text(
        client.get(reverse("agenda:calendar"))
    )


@pytest.mark.django_db
def test_calendar_shows_deadlines_questions_and_sends(
    user, client_record, request_record
):
    today = timezone.localdate()
    request_record.deadline = timezone.make_aware(
        datetime.combine(today + timedelta(days=3), time.max)
    )
    request_record.save()
    questions.ask(
        owner=user,
        client_id=client_record.pk,
        question="Za co przelew?",
        deadline=timezone.make_aware(
            datetime.combine(today + timedelta(days=5), time.max)
        ),
    )

    events = calendar.deadlines(user, today, today + timedelta(days=10))

    kinds = {event["kind"]: (day, event["label"]) for day, event in events}
    assert kinds["deadline"] == (
        today + timedelta(days=3),
        f"Termin: {request_record.name}",
    )
    assert kinds["question"] == (today + timedelta(days=5), "Pytanie: Za co przelew?")
    grid = calendar.month(user, today.year, today.month)
    assert len(grid["weeks"][0]) == 7 and grid["weeks"][0][0]["day"].weekday() == 0


@pytest.mark.django_db
def test_calendar_page_moves_between_months(client, user):
    client.force_login(user)

    page = _plain(page_text(client.get(reverse("agenda:calendar"), {"m": "2026-12"})))
    broken = client.get(reverse("agenda:calendar"), {"m": "nonsense"})

    assert "Grudzień 2026" in page
    assert broken.status_code == 200


# --- the phone's calendar ---------------------------------------------------------


@pytest.mark.django_db
def test_feed_by_secret_link_only(client, user, client_record):
    PersonalReminder.objects.create(
        account=user,
        author=user,
        client=client_record,
        text="Zadzwonić; w sprawie, umowy",
        due_on=timezone.localdate() + timedelta(days=2),
    )
    client.force_login(user)
    client.post(reverse("agenda:feed-link"))
    token = AgendaSettings.objects.get(user=user).feed_token
    client.logout()

    response = client.get(reverse("agenda:feed", args=[token]))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/calendar")
    body = response.content.decode()
    assert body.startswith("BEGIN:VCALENDAR\r\n") and body.endswith("END:VCALENDAR\r\n")
    assert "SUMMARY:Zadzwonić\\; w sprawie\\, umowy" in body.replace("\r\n ", "")
    assert client.get(reverse("agenda:feed", args=["zly-token"])).status_code == 404


@pytest.mark.django_db
def test_new_link_turns_the_old_one_off(client, user):
    client.force_login(user)
    client.post(reverse("agenda:feed-link"))
    old = AgendaSettings.objects.get(user=user).feed_token
    client.post(reverse("agenda:feed-link"))

    assert client.get(reverse("agenda:feed", args=[old])).status_code == 404


@pytest.mark.django_db
def test_feed_events_keep_their_uid(user, request_record):
    request_record.deadline = timezone.now() + timedelta(days=2)
    request_record.save()

    first = ics.feed_for(user, "https://monituj.pl")
    PersonalReminder.objects.create(
        account=user, author=user, text="Nowe", due_on=timezone.localdate()
    )
    second = ics.feed_for(user, "https://monituj.pl")

    uid = f"UID:deadline-{_local(request_record.deadline):%Y%m%d}-"
    assert uid in first
    line = next(row for row in first.split("\r\n") if row.startswith(uid))
    assert line in second


def _local(moment):
    return timezone.localtime(moment).date()


def test_long_lines_are_folded():
    line = "SUMMARY:" + "ą" * 80
    folded = ics._fold(line)
    assert all(len(part.encode()) <= 75 for part in folded.split("\r\n"))
    assert folded.replace("\r\n ", "") == line


# --- "Na dziś" -----------------------------------------------------------------------


@pytest.mark.django_db
def test_morning_email_at_half_past_seven_on_working_days(
    user, client_record, mailoutbox
):
    monday = _monday()
    PersonalReminder.objects.create(
        account=user, author=user, text="Zadzwonić do Nowaka", due_on=monday
    )

    assert digest.send_due(now=_at(monday, 7, 0)) == 0  # too early
    assert digest.send_due(now=_at(monday, 7, 35)) == 1
    assert digest.send_due(now=_at(monday, 9, 0)) == 0  # once a day
    saturday = monday + timedelta(days=5)
    assert digest.send_due(now=_at(saturday, 8, 0)) == 0

    email = mailoutbox[-1]
    assert email.to == [user.email]
    assert email.subject.startswith("Na dziś")
    assert "Zadzwonić do Nowaka" in _plain(email.body)


@pytest.mark.django_db
def test_morning_email_lists_long_waiting_questions_with_the_note(
    user, client_record, mailoutbox
):
    from apps.requests.models import Request

    asked = questions.ask(
        owner=user,
        client_id=client_record.pk,
        question="Za co przelew 1 250 zł?",
        note="VAT za wrzesień",
    )
    Request.objects.filter(pk=asked.pk).update(
        created_at=timezone.now() - timedelta(days=10)
    )

    assert digest.send_due(now=_at(_monday(), 7, 45)) == 1

    body = _plain(mailoutbox[-1].body)
    assert "Za co przelew 1 250 zł?" in body and "Po co: VAT za wrzesień" in body


@pytest.mark.django_db
def test_nothing_to_say_or_switched_off_means_no_email(client, user, mailoutbox):
    monday = _monday()
    assert digest.send_due(now=_at(monday, 8, 0)) == 0  # nothing to tell

    PersonalReminder.objects.create(
        account=user, author=user, text="Coś", due_on=monday + timedelta(days=1)
    )
    client.force_login(user)
    client.post(reverse("agenda:daily-email"), {})
    assert settings_for(user).daily_email is False
    assert digest.send_due(now=_at(monday + timedelta(days=1), 8, 0)) == 0
    assert mailoutbox == []
