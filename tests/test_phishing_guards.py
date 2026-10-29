"""Monituj can't be used to phish: names that mimic banks and offices are
refused however they are spelled, accounts that haven't paid can't ask for
PINs or bank passwords and write to few people in their first week, and
every recipient can report a request ("Zgłoś nadużycie")."""

import pytest
from django.core import mail
from django.urls import reverse

from apps.accounts import team
from apps.accounts.models import User
from apps.accounts.sender import is_deceptive
from apps.billing.services import account_for
from apps.clients.models import Client
from apps.common.exceptions import RateLimitedAppError
from apps.requests import abuse, content_rules
from apps.requests import services as request_services
from apps.requests.models import AbuseReason, AbuseReport, Request
from apps.requests.services import RequestService
from tests.conftest import page_text


def _subscribe(user):
    account = account_for(user)
    account.stripe_mode = "sandbox"
    account.stripe_customer_id = "cus_1"
    account.stripe_subscription_id = "sub_1"
    account.plan = "start"
    account.interval = "month"
    account.status = "active"
    account.save()


# --- names -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "mBank24",
        "m-bank",
        "M.Bank",
        "rnBank",
        "Urz4d Skarb0wy",
        "Urząd-Skarbowy",
        "РКО ВР",  # Cyrillic letters
        "PKO.BP",
        "Revolut24",
        "Mon1tuj",
        "1NG Bank",
    ],
)
def test_a_mimicked_name_is_refused_however_it_is_spelled(name):
    assert is_deceptive(name)


@pytest.mark.parametrize(
    "name",
    [
        "Adam Bankowski",
        "Tom Bańkowski",
        "Kancelaria 365",
        "Biuro 24",
        "Kasprzak Finanse",
        "Pinkowski Biuro",
        "Corn Office",
        "Biuro Komorowski",
        "Bookkeeping 3D",
    ],
)
def test_ordinary_names_still_pass(name):
    assert not is_deceptive(name)


@pytest.mark.django_db
def test_joining_a_team_refuses_a_mimicked_name(client, user, mailoutbox):
    team.invite(user, "anna@biuro.pl")
    link = mailoutbox[-1].body.split("/zespol/zaproszenie/", 1)[1].split("/", 1)[0]

    client.post(
        f"/zespol/zaproszenie/{link}/",
        {
            "name": "mBank24 - dział weryfikacji",
            "password": "Bardzo-Tajne-Haslo-1",
            "password_confirm": "Bardzo-Tajne-Haslo-1",
            "accept_terms": "on",
            "accept_privacy_policy": "on",
        },
    )

    assert not User.objects.filter(email="anna@biuro.pl").exists()


# --- what a request may ask for ----------------------------------------------------


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("Kod BLIK do potwierdzenia", "kod BLIK"),
        ("Podaj PIN do karty", "kod PIN"),
        ("P1N", "kod PIN"),
        ("Pełny numer karty kredytowej", "numer karty"),
        ("Kod CVV", "kod CVV"),
        ("Kod SMS z banku", "kod SMS"),
        ("Hasło do bankowości internetowej", "hasło do banku"),
        ("login do banku", "hasło do banku"),
        ("Wyciąg z karty kredytowej", None),
        ("Faktury sprzedaży", None),
        ("Token KSeF", None),
        ("Hasło do programu księgowego", None),
        ("Karta pojazdu", None),
        ("Lista płac - Pinkowski", None),
    ],
)
def test_what_counts_as_phishing(text, found):
    assert content_rules.found_in(text) == found


def _create(client, client_record, **fields):
    return client.post(
        reverse("requests:create"),
        {
            "client": client_record.pk,
            "name": "Dokumenty za wrzesień",
            "description": "",
            "items": ["Faktury sprzedaży"],
            "password": "",
            **fields,
        },
    )


@pytest.mark.django_db
def test_an_unpaid_account_cant_ask_for_a_blik_code(client, user, client_record):
    client.force_login(user)

    response = _create(client, client_record, items=["Faktury", "Kod BLIK"])

    assert not Request.objects.exists()
    assert "wyłudzenia" in page_text(response)


@pytest.mark.django_db
def test_the_description_is_checked_too(client, user, client_record):
    client.force_login(user)

    _create(client, client_record, description="Prześlij też hasło do banku.")

    assert not Request.objects.exists()


@pytest.mark.django_db
def test_a_paying_firm_is_not_held_back(client, user, client_record):
    _subscribe(user)
    client.force_login(user)

    _create(client, client_record, items=["Kod PIN do podpisu kwalifikowanego"])

    assert Request.objects.count() == 1


@pytest.mark.django_db
def test_a_question_is_checked(client, user, client_record):
    client.force_login(user)

    response = client.post(
        reverse("requests:question-create"),
        {
            "client": client_record.pk,
            "question": "Proszę o numer karty płatniczej i kod CVV.",
            "deadline_choice": "7",
            "reminder_preset": "standard",
        },
    )

    assert not Request.objects.exists()
    assert "wyłudzenia" in page_text(response)


@pytest.mark.django_db
def test_the_no_account_form_is_checked(client):
    response = client.post(
        reverse("public:guest-request-create"),
        {
            "sender_name": "Jan Kowalski",
            "sender_email": "jan@example.com",
            "client_name": "Anna",
            "client_email": "anna@example.com",
            "name": "Weryfikacja",
            "items": ["Kod SMS"],
            "accept_terms": "on",
        },
    )

    assert not Request.objects.exists()
    assert "wyłudzenia" in page_text(response)


# --- first week limits -------------------------------------------------------------


def _clients(user, count):
    return [
        Client.objects.create(owner=user, name=f"Klient {n}", email=f"k{n}@example.com")
        for n in range(count)
    ]


def _send(user, client_obj):
    return RequestService.create(
        owner=user,
        client_id=client_obj.pk,
        name="Dokumenty",
        description="",
        deadline=None,
        item_names=["Faktury"],
    )


@pytest.mark.django_db
def test_a_new_unpaid_account_writes_to_few_people(user, monkeypatch):
    monkeypatch.setattr(request_services, "NEW_ACCOUNT_RECIPIENTS", 2)
    first, second, third = _clients(user, 3)
    _send(user, first)
    _send(user, second)

    with pytest.raises(RateLimitedAppError) as exc_info:
        _send(user, third)
    assert exc_info.value.code == "RECIPIENT_LIMIT_REACHED"
    # A known recipient is fine - and nothing of the refused request stays.
    _send(user, first)
    assert Request.objects.filter(client=third).count() == 0


@pytest.mark.django_db
def test_many_clients_at_once_count_too(user, monkeypatch):
    monkeypatch.setattr(request_services, "NEW_ACCOUNT_RECIPIENTS", 2)
    clients = _clients(user, 3)

    with pytest.raises(RateLimitedAppError):
        RequestService.create_many(
            owner=user,
            client_ids=[c.pk for c in clients],
            name="Dokumenty",
            description="",
            deadline=None,
            item_names=["Faktury"],
        )
    assert not Request.objects.exists()


@pytest.mark.django_db
def test_paying_lifts_the_first_week_limits(user, monkeypatch):
    monkeypatch.setattr(request_services, "NEW_ACCOUNT_RECIPIENTS", 1)
    monkeypatch.setattr(request_services, "OUTBOUND_PER_DAY_NEW_ACCOUNT", 1)
    _subscribe(user)

    for client_obj in _clients(user, 3):
        _send(user, client_obj)

    assert Request.objects.count() == 3


@pytest.mark.django_db
def test_the_daily_limit_of_a_new_account_is_20():
    assert request_services.OUTBOUND_PER_DAY_NEW_ACCOUNT == 20
    assert request_services.NEW_ACCOUNT_RECIPIENTS == 20


# --- "Zgłoś nadużycie" -------------------------------------------------------------


@pytest.fixture
def alarms(settings):
    settings.SECURITY_ALERTS = True
    settings.SECURITY_EMAIL = "alarm@example.com"


def _alarms():
    return [m for m in mail.outbox if m.to == ["alarm@example.com"]]


@pytest.mark.django_db
def test_every_email_to_the_client_has_the_report_link(user, client_record):
    request_obj = _send(user, client_record)

    [invitation] = [m for m in mail.outbox if m.to == ["acme@example.com"]]
    link = abuse.report_url(request_obj)
    assert link in invitation.body
    assert link in invitation.alternatives[0][0]


@pytest.mark.django_db
def test_the_client_reports_and_the_team_hears_at_once(
    client, user, client_record, alarms
):
    request_obj = _send(user, client_record)
    url = reverse("public:report-abuse", args=[request_obj.public_token])

    page = client.get(url)
    response = client.post(
        url, {"reason": AbuseReason.SECRETS, "details": "Chcą kodu BLIK."}
    )

    assert "owner@example.com" in page_text(page)
    assert "Dziękujemy za zgłoszenie" in page_text(response)
    report = AbuseReport.objects.get()
    assert (report.sender_email, report.recipient_email) == (
        "owner@example.com",
        "acme@example.com",
    )
    [alarm] = _alarms()
    assert "owner@example.com" in alarm.subject
    assert "Chcą kodu BLIK." in alarm.body
    # Only an alarm: the account keeps working until the team decides.
    user.refresh_from_db()
    assert user.is_active


@pytest.mark.django_db
def test_the_report_link_works_behind_a_request_password(client, user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Dokumenty",
        description="",
        deadline=None,
        item_names=["Faktury"],
        password="tajne-haslo-123",
    )
    gate = client.get(reverse("public:request-detail", args=[request_obj.public_token]))
    url = reverse("public:report-abuse", args=[request_obj.public_token])

    assert url in page_text(gate)
    assert client.get(url).status_code == 200


@pytest.mark.django_db
def test_the_sender_previewing_their_page_sees_no_report_link(
    client, user, client_record
):
    request_obj = _send(user, client_record)
    url = reverse("public:report-abuse", args=[request_obj.public_token])
    page = reverse("public:request-detail", args=[request_obj.public_token])

    assert url in page_text(client.get(page))
    client.force_login(user)
    assert url not in page_text(client.get(page))


@pytest.mark.django_db
def test_reports_are_limited_per_address(client, user, client_record, monkeypatch):
    monkeypatch.setattr(abuse, "REPORTS_PER_IP_HOUR", 1)
    request_obj = _send(user, client_record)
    url = reverse("public:report-abuse", args=[request_obj.public_token])

    client.post(url, {"reason": AbuseReason.OTHER})
    response = client.post(url, {"reason": AbuseReason.OTHER})

    assert AbuseReport.objects.count() == 1
    assert "kilka zgłoszeń" in page_text(response)


@pytest.mark.django_db
def test_an_unknown_link_cant_be_reported(client):
    assert client.get("/d/nie-ma-takiego/zglos/").status_code == 404
