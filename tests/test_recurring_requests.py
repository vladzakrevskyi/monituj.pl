from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.services import account_for
from apps.clients.models import Client
from apps.requests import recurring
from apps.requests.models import RecurringInterval, RecurringRequest, Request

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
WARSAW = ZoneInfo("Europe/Warsaw")


def at(year, month, day, hour=9):
    return datetime(year, month, day, hour, tzinfo=WARSAW)


@pytest.fixture
def clients(user):
    return [
        Client.objects.create(owner=user, name=f"Klient {n}", email=f"k{n}@example.com")
        for n in range(1, 3)
    ]


def _plan(**timing):
    """An unsaved schedule - enough for the calendar functions."""
    return RecurringRequest(
        interval=timing.pop("interval", RecurringInterval.MONTHLY), **timing
    )


def _schedule(user, clients, due=date(2026, 10, 1), **timing):
    timing = {"interval": RecurringInterval.MONTHLY, "month_day": 1, **timing}
    schedule = RecurringRequest(
        owner=user,
        name="Dokumenty za {miesiąc}",
        item_names=["Faktury", "Wyciąg"],
        deadline_days=10,
        **timing,
    )
    recurring._set_next(schedule, due)
    schedule.save()
    schedule.clients.set(clients)
    return schedule


# --- the calendar ----------------------------------------------------


def test_polish_holidays():
    days = recurring.holidays(2026)
    assert date(2026, 4, 6) in days  # Poniedziałek Wielkanocny
    assert date(2026, 6, 4) in days  # Boże Ciało
    assert date(2026, 12, 24) in days  # Wigilia since 2025
    assert date(2024, 12, 24) not in recurring.holidays(2024)
    assert recurring.next_working_day(date(2026, 11, 1)) == date(2026, 11, 2)
    # Friday 1 May, Sunday 3 May: next working day is Monday 4 May.
    assert recurring.next_working_day(date(2026, 5, 1)) == date(2026, 5, 4)


def test_monthly_on_the_31st_is_the_last_day_of_shorter_months():
    plan = _plan(month_day=31)
    assert recurring.due_on_or_after(plan, date(2026, 2, 3)) == date(2026, 2, 28)
    assert recurring.due_on_or_after(plan, date(2028, 2, 3)) == date(2028, 2, 29)
    assert recurring.due_on_or_after(plan, date(2026, 11, 1)) == date(2026, 11, 30)
    assert recurring.describe(plan) == "co miesiąc, ostatniego dnia"


def test_a_day_off_moves_the_sending_not_the_schedule():
    plan = _plan(month_day=1, workdays_only=True)
    recurring._set_next(plan, date(2026, 11, 1))  # Sunday and a holiday
    assert plan.next_run_on == date(2026, 11, 2)
    # The next one is still the 1st of December.
    assert recurring.upcoming(plan) == [
        date(2026, 11, 2),
        date(2026, 12, 1),
        date(2027, 1, 4),  # 1 Jan holiday, 2-3 Jan weekend
    ]


def test_every_day_means_working_days():
    plan = _plan(interval=RecurringInterval.DAILY, workdays_only=True)
    recurring._set_next(plan, date(2026, 12, 23))
    assert recurring.upcoming(plan, 4) == [
        date(2026, 12, 23),
        date(2026, 12, 28),  # 24-27 off
        date(2026, 12, 29),
        date(2026, 12, 30),
    ]
    every = _plan(interval=RecurringInterval.DAILY, workdays_only=False)
    recurring._set_next(every, date(2026, 12, 24))
    assert recurring.upcoming(every, 2) == [date(2026, 12, 24), date(2026, 12, 25)]


def test_every_two_weeks_keeps_its_rhythm():
    plan = _plan(interval=RecurringInterval.BIWEEKLY, weekday=4, workdays_only=True)
    recurring.start(plan, date(2026, 9, 29), send_now=False)  # a Tuesday
    assert plan.anchor_on == date(2026, 10, 2)  # Friday
    assert recurring.upcoming(plan) == [
        date(2026, 10, 2),
        date(2026, 10, 16),
        date(2026, 10, 30),
    ]
    assert recurring.describe(plan) == "co 2 tygodnie w piątek"
    # Sent today: the rhythm starts a week later, not in three days.
    later = _plan(interval=RecurringInterval.BIWEEKLY, weekday=4)
    recurring.start(later, date(2026, 9, 29), send_now=True)
    assert later.next_run_on == date(2026, 10, 9)


def test_weekly():
    plan = _plan(interval=RecurringInterval.WEEKLY, weekday=0, workdays_only=True)
    recurring.start(plan, date(2026, 9, 29), send_now=False)
    assert recurring.upcoming(plan) == [
        date(2026, 10, 5),
        date(2026, 10, 12),
        date(2026, 10, 19),
    ]


def test_names():
    assert recurring.render_name("Dokumenty za {miesiąc}", date(2026, 10, 1)) == (
        "Dokumenty za wrzesień 2026"
    )
    assert recurring.render_name("Za {miesiac}", date(2027, 1, 5)) == (
        "Za grudzień 2026"
    )
    assert recurring.render_name("Raport {data}", date(2026, 10, 5)) == (
        "Raport 05.10.2026"
    )


# --- creating from the form -------------------------------------------


def _create(client, clients, **extra):
    data = {
        "recipients": "many",
        "clients": [c.pk for c in clients],
        "name": "Dokumenty za {miesiąc}",
        "items": ["Faktury", "Wyciąg"],
        "retention_choice": "90",
        "schedule": "recurring",
        "interval": "monthly",
        "month_day": "1",
        "weekday": "0",
        "workdays_only": "on",
        "deadline_days": "10",
        **extra,
    }
    return client.post(reverse("requests:create"), data, **AJAX)


@pytest.mark.django_db
def test_saved_and_first_sent_now(client, user, clients):
    client.force_login(user)

    response = _create(client, clients, send_first_now="on")

    assert response.json()["data"]["redirect_url"] == reverse("requests:list")
    schedule = RecurringRequest.objects.get()
    assert set(schedule.clients.all()) == set(clients)
    today = timezone.localdate()
    assert schedule.next_due_on.day == 1 and schedule.next_due_on > today
    sent = Request.objects.all()
    assert sent.count() == 2
    assert all(r.recurring == schedule for r in sent)
    assert all(r.name == f"Dokumenty za {recurring.month_label(today)}" for r in sent)
    assert all(r.deadline.date() == today + timedelta(days=10) for r in sent)


@pytest.mark.django_db
def test_every_two_weeks_from_the_form(client, user, clients):
    client.force_login(user)

    _create(client, clients, interval="biweekly", weekday="2")

    schedule = RecurringRequest.objects.get()
    assert schedule.interval == "biweekly"
    assert schedule.weekday == 2 and schedule.month_day is None
    assert schedule.anchor_on.weekday() == 2
    assert not Request.objects.exists()


@pytest.mark.django_db
def test_one_new_client_can_get_a_recurring_request(client, user):
    client.force_login(user)

    _create(
        client,
        [],
        recipients="one",
        new_client_email="nowy@firma.pl",
        new_client_name="Nowy",
    )

    schedule = RecurringRequest.objects.get()
    assert [c.email for c in schedule.clients.all()] == ["nowy@firma.pl"]


@pytest.mark.django_db
def test_no_password_and_a_day_is_needed(client, user, clients):
    client.force_login(user)

    response = _create(client, clients, password="Tajne-haslo-1", month_day="")

    fields = response.json()["error"]["fields"]
    assert "password" in fields and "month_day" in fields
    assert not RecurringRequest.objects.exists()


@pytest.mark.django_db
def test_once_is_still_an_ordinary_request(client, user, clients):
    client.force_login(user)

    _create(client, clients, schedule="once")

    assert not RecurringRequest.objects.exists()
    assert Request.objects.count() == 2


# --- the run ----------------------------------------------------------------------


@pytest.mark.django_db
def test_runs_on_its_day_from_eight_once(user, clients):
    schedule = _schedule(user, clients)

    assert recurring.run_due(at(2026, 10, 1, hour=7)) == 0
    assert recurring.run_due(at(2026, 10, 1, hour=8)) == 1
    assert recurring.run_due(at(2026, 10, 1, hour=12)) == 0

    schedule.refresh_from_db()
    assert schedule.next_due_on == date(2026, 11, 1)
    assert schedule.next_run_on == date(2026, 11, 2)  # 1 Nov: Sunday, holiday
    assert sorted(Request.objects.values_list("name", flat=True)) == [
        "Dokumenty za wrzesień 2026",
        "Dokumenty za wrzesień 2026",
    ]
    assert Request.objects.filter(invitation_queued=True).count() == 2


@pytest.mark.django_db
def test_a_moved_day_runs_on_the_working_day(user, clients):
    schedule = _schedule(user, clients, due=date(2026, 11, 1))

    assert recurring.run_due(at(2026, 11, 1)) == 0
    assert recurring.run_due(at(2026, 11, 2)) == 1

    schedule.refresh_from_db()
    assert schedule.next_due_on == date(2026, 12, 1)


@pytest.mark.django_db
def test_missed_days_are_not_caught_up(user, clients):
    schedule = _schedule(
        user, clients, due=date(2026, 9, 28), interval="daily", month_day=None
    )

    recurring.run_due(at(2026, 10, 5))

    schedule.refresh_from_db()
    assert Request.objects.count() == 2
    assert schedule.next_run_on == date(2026, 10, 6)


@pytest.mark.django_db
def test_paused_does_not_run(user, clients):
    _schedule(user, clients, active=False)

    assert recurring.run_due(at(2026, 10, 1)) == 0
    assert not Request.objects.exists()


@pytest.mark.django_db
def test_no_free_places_skips_the_period_and_tells_the_owner(user, clients):
    account = account_for(user)
    account.trial_ends_at = timezone.now() - timedelta(days=1)
    account.save()
    for number in range(2):  # Free: 3 in progress, 2 already used
        request_obj = Request.objects.create(
            client=clients[0], created_by=user, name=f"S{number}"
        )
        request_obj.items.create(name="F")
    schedule = _schedule(user, clients)

    recurring.run_due(at(2026, 10, 1))

    schedule.refresh_from_db()
    assert Request.objects.count() == 2
    assert "wolnych miejsc zostało 1" in schedule.last_result["skipped"]
    assert schedule.next_due_on == date(2026, 11, 1)
    [email] = mail.outbox
    assert email.to == [user.email]
    assert "Nie wysłaliśmy prośby cyklicznej" in email.subject


# --- on the list ------------------------------------------------------------------


@pytest.mark.django_db
def test_sent_requests_say_how_they_recur_in_the_list(client, user, clients):
    schedule = _schedule(user, clients)
    request_obj = Request.objects.create(
        client=clients[0], created_by=user, name="Z harmonogramu", recurring=schedule
    )
    request_obj.items.create(name="F")
    client.force_login(user)

    page = client.get(reverse("requests:list")).content.decode()
    detail = client.get(reverse("requests:detail", args=[request_obj.pk]))

    assert ">Cykliczna</span>" in page
    assert "co miesiąc, 1. dnia · następna" in page
    assert reverse("requests:recurring-edit", args=[schedule.pk]) in page
    # Sent already: no separate "planned" row for it.
    assert "Zaplanowana" not in page
    assert "Harmonogram: wyślij teraz" in detail.content.decode()


@pytest.mark.django_db
def test_a_schedule_that_sent_nothing_yet_is_a_planned_row(client, user, clients):
    _schedule(user, clients)
    client.force_login(user)

    page = client.get(reverse("requests:list")).content.decode()
    filtered = client.get(reverse("requests:list"), {"q": "nic takiego"})

    assert "Zaplanowana" in page
    assert "· pierwsza " in page
    assert "Brak przypomnień." not in page
    assert "Zaplanowana" not in filtered.content.decode()


@pytest.mark.django_db
def test_send_now_is_extra_and_leaves_the_schedule_alone(client, user, clients):
    today = timezone.localdate()
    day = min(today.day, 28)
    schedule = _schedule(
        user, clients, due=today.replace(day=day), month_day=day, workdays_only=False
    )
    before = (schedule.next_due_on, schedule.next_run_on, schedule.last_run_at)
    client.force_login(user)

    response = client.post(reverse("requests:recurring-send", args=[schedule.pk]))

    schedule.refresh_from_db()
    assert response["Location"] == reverse(
        "requests:recurring-edit", args=[schedule.pk]
    )
    assert Request.objects.filter(recurring=schedule).count() == 2
    assert (schedule.next_due_on, schedule.next_run_on, schedule.last_run_at) == before


@pytest.mark.django_db
def test_pause_resume_edit_delete(client, user, clients):
    schedule = _schedule(user, clients, due=date(2026, 1, 1))
    client.force_login(user)

    client.post(reverse("requests:recurring-toggle", args=[schedule.pk]))
    schedule.refresh_from_db()
    paused = schedule.active
    client.post(reverse("requests:recurring-toggle", args=[schedule.pk]))
    schedule.refresh_from_db()
    edited = client.post(
        reverse("requests:recurring-edit", args=[schedule.pk]),
        {
            "name": "Kadry za {miesiąc}",
            "items": ["Listy obecności"],
            "clients": [clients[0].pk],
            "interval": "weekly",
            "weekday": "3",
            "month_day": "1",
            "deadline_days": "",
            "retention_choice": "90",
        },
        **AJAX,
    )
    after_edit = RecurringRequest.objects.get()
    edited_clients = list(after_edit.clients.all())
    client.post(reverse("requests:recurring-delete", args=[schedule.pk]))

    assert paused is False
    # Resumed after its day: the next one ahead, no catching up.
    assert schedule.active and schedule.next_run_on >= timezone.localdate()
    assert edited.status_code == 200
    assert after_edit.name == "Kadry za {miesiąc}"
    assert after_edit.interval == "weekly" and after_edit.weekday == 3
    assert after_edit.month_day is None
    assert after_edit.next_due_on.weekday() == 3
    assert edited_clients == [clients[0]]
    assert not RecurringRequest.objects.exists()


@pytest.mark.django_db
def test_someone_elses_schedule_is_not_found(client, user, clients):
    schedule = _schedule(user, clients)
    stranger = User.objects.create_user(email="obcy@example.com", password="x-pass-1!")
    client.force_login(stranger)

    for name in ("recurring-send", "recurring-toggle", "recurring-delete"):
        url = reverse(f"requests:{name}", args=[schedule.pk])
        assert client.post(url).status_code == 404
    edit = reverse("requests:recurring-edit", args=[schedule.pk])
    assert client.get(edit).status_code == 404
    assert RecurringRequest.objects.get().active
