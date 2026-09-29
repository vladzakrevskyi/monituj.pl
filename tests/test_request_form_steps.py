from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.clients.models import Client
from apps.requests import recurring
from apps.requests.forms import next_month_day
from apps.requests.models import RecurringRequest, Request, RequestItem
from apps.requests.views import suggested_items

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


@pytest.fixture
def clients(user):
    return [
        Client.objects.create(owner=user, name=f"Klient {n}", email=f"k{n}@example.com")
        for n in range(1, 3)
    ]


def _post(client, **data):
    base = {
        "name": "Dokumenty",
        "items": ["Faktury"],
        "retention_choice": "90",
        "reminder_preset": "standard",
        "deadline_choice": "14",
    }
    return client.post(reverse("requests:create"), {**base, **data}, **AJAX)


# --- one field for one client or many ----------


@pytest.mark.django_db
def test_one_client_picked_is_a_single_request_with_a_password(client, user, clients):
    client.force_login(user)

    response = _post(client, clients=[clients[0].pk], password="Tajne-haslo-1")

    request_obj = Request.objects.get()
    assert response.json()["data"]["redirect_url"] == reverse(
        "requests:detail", args=[request_obj.pk]
    )
    assert request_obj.is_password_protected
    assert not request_obj.invitation_queued


@pytest.mark.django_db
def test_several_picked_go_to_each_but_without_a_password(client, user, clients):
    client.force_login(user)

    refused = _post(client, clients=[c.pk for c in clients], password="Tajne-haslo-1")
    sent = _post(client, clients=[c.pk for c in clients])

    assert "password" in refused.json()["error"]["fields"]
    assert sent.status_code == 200
    assert Request.objects.count() == 2


@pytest.mark.django_db
def test_a_typed_address_of_a_known_client_is_that_client(client, user, clients):
    client.force_login(user)

    _post(
        client,
        clients=[clients[0].pk],
        new_clients_email=[clients[0].email.upper(), "nowy@firma.pl"],
        new_clients_name=["", "Nowy"],
    )

    assert Client.objects.count() == 3
    assert Request.objects.count() == 2


# --- the deadline buttons ----------


@pytest.mark.parametrize(("choice", "days"), [("7", 7), ("14", 14)])
@pytest.mark.django_db
def test_deadline_in_days(client, user, clients, choice, days):
    client.force_login(user)

    _post(client, clients=[clients[0].pk], deadline_choice=choice)

    deadline = Request.objects.get().deadline
    assert timezone.localtime(deadline).date() == timezone.localdate() + timedelta(
        days=days
    )


@pytest.mark.django_db
def test_deadline_on_the_10th_and_none_and_a_date(client, user, clients):
    client.force_login(user)

    _post(client, clients=[clients[0].pk], deadline_choice="day10", name="A")
    _post(client, clients=[clients[0].pk], deadline_choice="none", name="B")
    missing = _post(client, clients=[clients[0].pk], deadline_choice="date", name="C")
    _post(
        client,
        clients=[clients[0].pk],
        deadline_choice="date",
        deadline="2030-05-17",
        name="D",
    )

    tenth = Request.objects.get(name="A").deadline
    assert timezone.localtime(tenth).day == 10
    assert timezone.localtime(tenth).date() > timezone.localdate()
    assert Request.objects.get(name="B").deadline is None
    assert "deadline" in missing.json()["error"]["fields"]
    assert timezone.localtime(Request.objects.get(name="D").deadline).date() == (
        date(2030, 5, 17)
    )


def test_next_10th():
    assert next_month_day(date(2026, 10, 3), 10) == date(2026, 10, 10)
    assert next_month_day(date(2026, 10, 10), 10) == date(2026, 11, 10)
    assert next_month_day(date(2026, 12, 20), 10) == date(2027, 1, 10)


@pytest.mark.django_db
def test_recurring_deadline_until_the_10th(client, user, clients):
    client.force_login(user)

    _post(
        client,
        clients=[clients[0].pk],
        schedule="recurring",
        interval="monthly",
        month_day="1",
        deadline_choice="day10",
        send_first_now="on",
    )

    schedule = RecurringRequest.objects.get()
    assert schedule.deadline_month_day == 10 and schedule.deadline_days is None
    assert recurring.describe_deadline(schedule) == "termin: do 10. dnia miesiąca"
    assert timezone.localtime(Request.objects.get().deadline).day == 10


# --- reminders ----------


@pytest.mark.parametrize(
    ("preset", "expected"),
    [
        ("gentle", (True, 3, 5, 2)),
        ("frequent", (True, 1, 2, 5)),
        ("off", (False, 2, 3, 3)),
    ],
)
@pytest.mark.django_db
def test_reminder_presets(client, user, clients, preset, expected):
    client.force_login(user)

    _post(client, clients=[clients[0].pk], reminder_preset=preset)

    r = Request.objects.get()
    assert (
        r.reminders_enabled,
        r.first_reminder_after_days,
        r.reminder_frequency_days,
        r.max_reminders,
    ) == expected


@pytest.mark.django_db
def test_custom_reminders(client, user, clients):
    client.force_login(user)

    _post(
        client,
        clients=[clients[0].pk],
        reminder_preset="custom",
        first_reminder_after_days="4",
        reminder_frequency_days="6",
        max_reminders="7",
    )

    r = Request.objects.get()
    assert (r.reminders_enabled, r.first_reminder_after_days, r.max_reminders) == (
        True,
        4,
        7,
    )


# --- remembered settings and suggestions ----------


@pytest.mark.django_db
def test_the_form_starts_with_the_last_used_settings(client, user, clients):
    client.force_login(user)
    _post(
        client,
        clients=[clients[0].pk],
        reminder_preset="frequent",
        retention_choice="180",
    )

    page = client.get(reverse("requests:create")).content.decode()

    assert 'name="reminder_preset" value="frequent" checked' in page
    assert '<option value="180" selected>' in page


@pytest.mark.django_db
def test_suggestions_start_with_the_owners_own_documents(user, client_record):
    request_obj = Request.objects.create(
        client=client_record, created_by=user, name="R"
    )
    for name in ("Umowa najmu", "Umowa najmu", "Faktury sprzedaży"):
        RequestItem.objects.create(request=request_obj, name=name)

    names = suggested_items(user)

    assert names[0] == "Umowa najmu"
    assert names.count("Faktury sprzedaży") == 1
    assert len(names) == 8
