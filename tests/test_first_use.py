"""What a new user meets: the panel's first steps and to-do, the request page
after sending, the client's link as the sender sees it, the reminder plan
and the names the panel gives things."""

from datetime import date, timedelta

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent, AuditLog
from apps.documents.services import UploadDocumentService
from apps.reminders.services import ReminderScheduleService
from apps.requests import questions, recurring
from apps.requests.models import Request
from apps.requests.services import DashboardService, RequestService
from tests.conftest import make_pdf_upload, page_text

PASSWORD = "Mocne-Haslo-2026!"
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def _send(owner, client_record, name="Dokumenty za wrzesień", deadline=None):
    return RequestService.create(
        owner=owner,
        client_id=client_record.pk,
        name=name,
        description="",
        deadline=deadline,
        item_names=["Wyciąg", "Faktury"],
    )


# --- addresses ---------------------------------------------------------------


@pytest.mark.django_db
def test_old_panel_links_lead_to_prosby(client, user, request_record):
    client.force_login(user)

    response = client.get(f"/przypomnienia/{request_record.pk}/?widok=1")

    assert response.status_code == 301
    assert response["Location"] == f"/prosby/{request_record.pk}/?widok=1"


@pytest.mark.django_db
def test_a_question_lives_under_pytania(client, user, client_record):
    asked = questions.ask(user, client_record.pk, "Co to za przelew z 12.09?")
    client.force_login(user)

    response = client.get(reverse("requests:detail", args=[asked.pk]))

    assert response["Location"] == f"/pytania/{asked.pk}/"


@pytest.mark.django_db
def test_a_request_is_not_shown_under_pytania(client, user, request_record):
    client.force_login(user)

    response = client.get(f"/pytania/{request_record.pk}/")

    assert response["Location"] == f"/prosby/{request_record.pk}/"


@pytest.mark.django_db
def test_the_menu_says_prosby(client, user):
    client.force_login(user)

    page = page_text(client.get(reverse("requests:list")))

    assert "Prośby" in page and "Nowa prośba" in page
    assert "Nowe przypomnienie" not in page


# --- the panel ---------------------------------------------------------------


@pytest.mark.django_db
def test_a_new_account_sees_first_steps(client, user):
    client.force_login(user)

    page = page_text(client.get(reverse("accounts:panel")))

    assert "Pierwsze kroki" in page and "0 z 2" in page
    assert "Wyślij pierwszą prośbę" in page and "Zaimportuj ją" in page
    # Nothing sent yet: no row of zeros.
    assert "Brakujące dokumenty" not in page


@pytest.mark.django_db
def test_first_steps_go_once_a_document_arrives(user, client_record):
    request_obj = _send(user, client_record)
    steps = DashboardService.first_steps(user)
    assert steps["done"] == 1
    assert steps["public_url"].endswith(f"/d/{request_obj.public_token}/")

    item = request_obj.items.first()
    UploadDocumentService.upload_for_item(item, make_pdf_upload())

    assert DashboardService.first_steps(user) is None


@pytest.mark.django_db
def test_to_do_lists_answers_documents_and_overdue(user, client_record):
    _send(
        user,
        client_record,
        name="Spóźniona",
        deadline=timezone.now() - timedelta(days=2),
    )
    sent = _send(user, client_record, name="Z plikiem")
    UploadDocumentService.upload_for_item(sent.items.first(), make_pdf_upload())
    asked = questions.ask(user, client_record.pk, "Co to za przelew z 12.09?")
    questions.answer(asked.question_item, "Zaliczka za mąkę")

    to_do = DashboardService.to_do(user)

    kinds = [entry["kind"] for entry in to_do]
    assert kinds == ["answer", "review", "overdue"]
    assert "Zaliczka za mąkę" in to_do[0]["meta"]
    assert to_do[0]["url"] == f"/pytania/{asked.pk}/"
    assert "1 pozycja czeka" in to_do[1]["meta"]
    assert to_do[2]["title"] == "Spóźniona" and "brakuje 2" in to_do[2]["meta"]


@pytest.mark.django_db
def test_activity_is_about_clients_not_logins(client, user, client_record):
    request_obj = _send(user, client_record)
    client.force_login(user)
    for _ in range(3):
        client.get(f"/d/{request_obj.public_token}/")  # the owner: not counted
    AuditLog.objects.create(event=AuditEvent.USER_LOGIN, actor=user)
    for _ in range(3):
        AuditLog.objects.create(
            event=AuditEvent.PUBLIC_LINK_ACCESSED,
            content_type_id=_request_type(),
            object_id=request_obj.pk,
        )

    events = [entry.event for entry in DashboardService.activity(user)]

    assert AuditEvent.USER_LOGIN not in events
    assert events.count(AuditEvent.PUBLIC_LINK_ACCESSED) == 1
    assert AuditEvent.REQUEST_CREATED in events


def _request_type():
    from django.contrib.contenttypes.models import ContentType

    return ContentType.objects.get_for_model(Request).pk


# --- the client's link, opened by the sender -----------------------------------


@pytest.mark.django_db
def test_the_sender_previews_without_counting_as_the_client(
    client, user, client_record
):
    request_obj = _send(user, client_record)
    client.force_login(user)

    page = page_text(client.get(f"/d/{request_obj.public_token}/"))

    assert "Tak tę stronę widzi Twój klient" in page
    assert not AuditLog.objects.filter(event=AuditEvent.PUBLIC_LINK_ACCESSED).exists()


@pytest.mark.django_db
def test_the_client_sees_no_site_menu(client, user, client_record):
    request_obj = _send(user, client_record)

    page = page_text(client.get(f"/d/{request_obj.public_token}/"))

    assert "Tak tę stronę widzi" not in page
    assert "Zacznij za darmo" not in page and "Cennik" not in page
    assert AuditLog.objects.filter(event=AuditEvent.PUBLIC_LINK_ACCESSED).count() == 1


@pytest.mark.django_db
def test_request_page_says_what_happens_next(client, user, client_record):
    request_obj = _send(user, client_record)
    client.force_login(user)

    page = page_text(client.get(reverse("requests:detail", args=[request_obj.pk])))

    assert "Wysłane do acme@example.com" in page
    assert "Klient jeszcze nie otworzył linku" in page
    assert "Zobacz, co widzi klient" in page


# --- the reminder plan ---------------------------------------------------------


@pytest.mark.django_db
def test_planned_reminders_never_twice_the_same_day(user, client_record):
    """The audit's case: a question due in 7 days, reminders after 2 and every
    3 days - the second interval one and the one 2 days before the deadline
    fall on the same day: only one goes out."""
    asked = questions.ask(
        user,
        client_record.pk,
        "Co to za przelew z 12.09?",
        deadline=timezone.now() + timedelta(days=7),
    )
    Request.objects.filter(pk=asked.pk).update(
        first_reminder_after_days=2, reminder_frequency_days=3, max_reminders=3
    )
    asked.refresh_from_db()

    planned = ReminderScheduleService.planned(asked)

    days = [entry["at"].date() for entry in planned]
    assert len(days) == len(set(days))
    kinds = [entry["kind"] for entry in planned]
    assert "deadline_day" in kinds
    after = [e for e in planned if e["at"] > asked.deadline]
    assert all(e["kind"] == "after_deadline" for e in after)


# --- names ---------------------------------------------------------------------


@pytest.mark.django_db
def test_the_month_is_the_one_before_the_deadline(client, user, client_record):
    client.force_login(user)
    deadline = timezone.localdate() + timedelta(days=40)

    client.post(
        reverse("requests:create"),
        {
            "client": client_record.pk,
            "name": "Dokumenty za {miesiąc}",
            "items": ["A"],
            "deadline_choice": "date",
            "deadline": deadline.isoformat(),
            "retention_choice": "90",
        },
        **AJAX,
    )

    name = Request.objects.get().name
    assert name == f"Dokumenty za {recurring.month_label(deadline)}"


def test_month_label_is_the_previous_month():
    assert recurring.month_label(date(2026, 11, 10)) == "październik 2026"


def test_client_statuses_say_what_they_mean():
    from apps.clients.services import ClientStatus

    assert ClientStatus.MISSING_DOCUMENTS.label == "Nic nie przesłano"
    assert ClientStatus.ACTIVE.label == "W trakcie"


# --- signing up ----------------------------------------------------------------


def _register(client, email="nowy@example.com"):
    return client.post(
        reverse("accounts:register"),
        {
            "email": email,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "accept_terms": "on",
            "accept_privacy_policy": "on",
        },
    )


@pytest.mark.django_db
def test_check_your_inbox_names_the_address_and_resends(client):
    _register(client)
    assert len(mail.outbox) == 1

    page = page_text(client.get(reverse("accounts:verification-sent")))
    assert "nowy@example.com" in page and "Spam" in page

    client.post(reverse("accounts:verification-sent"))
    client.post(reverse("accounts:verification-sent"))  # too soon

    assert len(mail.outbox) == 2


@pytest.mark.django_db
def test_no_resend_for_an_account_someone_else_registered(client):
    User.objects.create_user(email="cudzy@example.com", password=PASSWORD)
    _register(client, "cudzy@example.com")
    sent = len(mail.outbox)

    page = page_text(client.get(reverse("accounts:verification-sent")))
    client.post(reverse("accounts:verification-sent"))

    assert "Wyślij link ponownie" not in page
    assert len(mail.outbox) == sent
