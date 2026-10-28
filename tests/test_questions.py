"""Questions to a client (apps/requests/questions.py): the sender asks with a
note of why, the client answers in words from the link, the sender sees the
question, the note and the answer together - and marks it "Wyjaśnione" or
asks a follow-up."""

import json
import re

import pytest
from django.urls import reverse

from apps.notifications.inbox import send_pending_upload_emails
from apps.notifications.models import Notification, NotificationKind
from apps.requests import questions
from apps.requests.models import RequestItemKind, RequestItemStatus
from tests.conftest import page_text

QUESTION = (
    "Na wyciągu z mBanku za wrzesień jest przelew 1 250,00 zł z 12.09 dla "
    "„Jan Nowak”.\nZa co była ta płatność?"
)
NOTE = "Wrzesień, VAT - jeśli koszt, szukać faktury."
JSON = "application/json"


def _plain(text):
    return text.replace(" ", " ")


@pytest.fixture
def asked(user, client_record, mailoutbox):
    request_obj = questions.ask(
        owner=user, client_id=client_record.pk, question=QUESTION, note=NOTE
    )
    return request_obj


def _answer(client, request_obj, text="To zaliczka za remont, faktura w załączniku."):
    client.get(f"/d/{request_obj.public_token}/")
    item = request_obj.question_item
    return client.post(
        f"/api/public/{request_obj.public_token}/items/{item.pk}/answer/",
        json.dumps({"answer": text}),
        content_type=JSON,
    )


# --- asking ---------------------------------------------------------------------------


def test_title_is_the_first_line_shortened():
    assert questions.title_of("Za co przelew?\nszczegóły") == "Za co przelew?"
    long = "słowo " * 40
    title = questions.title_of(long)
    assert len(title) <= questions.TITLE_LENGTH and title.endswith("…")


@pytest.mark.django_db
def test_asking_makes_a_one_question_request_and_emails_the_question(
    asked, client_record, mailoutbox
):
    item = asked.question_item
    assert asked.items.count() == 1
    assert item.kind == RequestItemKind.QUESTION
    assert item.description == QUESTION
    assert asked.name.startswith("Na wyciągu z mBanku")
    assert asked.private_note == NOTE

    invitation = mailoutbox[-1]
    assert invitation.to == [client_record.email]
    assert invitation.subject.startswith("Pytanie")
    body = _plain(invitation.body)
    assert "Za co była ta płatność?" in body
    assert "Potrzebne dokumenty" not in body
    # The sender's note never reaches the client.
    assert NOTE not in body
    assert all(NOTE not in _plain(str(alt[0])) for alt in invitation.alternatives)


@pytest.mark.django_db
def test_form_sends_the_question(client, user, client_record):
    client.force_login(user)

    response = client.post(
        reverse("requests:question-create"),
        {
            "client": client_record.pk,
            "question": QUESTION,
            "note": NOTE,
            "deadline_choice": "7",
            "reminder_preset": "standard",
        },
    )

    request_obj = user.requests.get()
    assert response.status_code == 302
    assert response["Location"] == reverse(
        "requests:question-detail", args=[request_obj.pk]
    )
    assert request_obj.deadline is not None
    assert request_obj.reminders_enabled


@pytest.mark.django_db
def test_form_needs_a_question_and_a_date_when_chosen(client, user, client_record):
    client.force_login(user)

    response = client.post(
        reverse("requests:question-create"),
        {"client": client_record.pk, "question": "", "deadline_choice": "date"},
    )

    text = page_text(response)
    assert "Napisz pytanie do klienta." in text
    assert "Wybierz datę." in text
    assert not user.requests.exists()


@pytest.mark.django_db
def test_form_offers_only_ones_own_clients(client, user, client_record):
    from apps.accounts.models import User
    from apps.clients.models import Client

    stranger = User.objects.create_user(email="obcy@example.com", password="x")
    foreign = Client.objects.create(owner=stranger, name="Obcy", email="o@example.com")
    client.force_login(user)

    page = client.get(reverse("requests:question-create")).content.decode()
    response = client.post(
        reverse("requests:question-create"),
        {"client": foreign.pk, "question": QUESTION, "deadline_choice": "none"},
    )

    assert "Obcy" not in page
    assert "Wybierz klienta z listy." in page_text(response)


# --- the client's side -----------------------------------------------------------


@pytest.mark.django_db
def test_client_page_shows_the_question_and_never_the_note(client, asked):
    page = _plain(client.get(f"/d/{asked.public_token}/").content.decode())

    assert "Za co była ta płatność?" in page
    assert "data-answer-form" in page
    assert NOTE not in page
    assert "Nie mam tego dokumentu" not in page


@pytest.mark.django_db
def test_client_answers_and_the_sender_gets_question_note_and_answer(
    client, user, asked, mailoutbox
):
    mailoutbox.clear()

    response = _answer(client, asked)

    assert response.status_code == 200
    assert response.json()["data"]["item"]["status"]["label"] == "Odpowiedziano"
    item = asked.question_item
    item.refresh_from_db()
    assert item.status == RequestItemStatus.DOSTARCZONY
    assert item.answer.startswith("To zaliczka")
    assert item.answered_at is not None
    notice = Notification.objects.get(kind=NotificationKind.ANSWERED)
    assert send_pending_upload_emails(now=notice.created_at.replace(year=2100)) == 1
    email = mailoutbox[-1]
    assert email.to == [user.email]
    assert email.subject.startswith("Klient odpowiedział")
    body = _plain(email.body)
    assert "Za co była ta płatność?" in body
    assert NOTE in body  # the sender's own email: the note is theirs
    assert "To zaliczka za remont" in body
    # No "komplet dokumentów" for a question.
    assert not any("komplet" in m.subject.lower() for m in mailoutbox)


@pytest.mark.django_db
def test_answer_can_be_corrected_until_accepted(client, asked):
    _answer(client, asked, "Pierwsza wersja")
    _answer(client, asked, "Poprawiona odpowiedź")
    item = asked.question_item
    item.refresh_from_db()
    assert item.answer == "Poprawiona odpowiedź"
    assert Notification.objects.filter(kind=NotificationKind.ANSWERED).count() == 1

    from apps.documents.services import DocumentReviewService

    DocumentReviewService.accept(item)
    assert _answer(client, asked, "Jeszcze raz").status_code == 400


@pytest.mark.django_db
def test_empty_answer_and_not_a_question(client, asked, request_record, request_item):
    assert _answer(client, asked, "   ").status_code == 400

    client.get(f"/d/{request_record.public_token}/")
    response = client.post(
        f"/api/public/{request_record.public_token}/items/{request_item.pk}/answer/",
        json.dumps({"answer": "x"}),
        content_type=JSON,
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_answer_needs_the_opened_link(client, asked):
    item = asked.question_item

    response = client.post(
        f"/api/public/{asked.public_token}/items/{item.pk}/answer/",
        json.dumps({"answer": "x"}),
        content_type=JSON,
    )

    assert response.status_code == 403


# --- the sender's side -----------------------------------------------------------


@pytest.mark.django_db
def test_follow_up_goes_to_the_client_and_they_answer_again(client, asked, mailoutbox):
    from apps.documents.services import DocumentReviewService

    _answer(client, asked)
    item = asked.question_item
    item.refresh_from_db()

    DocumentReviewService.reject(item, "Czy faktura jest na firmę?")

    email = mailoutbox[-1]
    assert email.subject.startswith("Pytanie uzupełniające")
    body = _plain(email.body)
    assert "Czy faktura jest na firmę?" in body and "Za co była ta płatność?" in body
    assert NOTE not in body
    page = _plain(client.get(f"/d/{asked.public_token}/").content.decode())
    assert "Pytanie uzupełniające" in page and "Czy faktura jest na firmę?" in page
    assert _answer(client, asked, "Tak, NIP jest na fakturze.").status_code == 200


@pytest.mark.django_db
def test_the_conversation_keeps_every_message(client, user, asked):
    from apps.documents.services import DocumentReviewService

    _answer(client, asked, "To zaliczka za remont.")
    item = asked.question_item
    item.refresh_from_db()
    DocumentReviewService.reject(item, "Czy faktura jest na firmę?")
    _answer(client, asked, "Tak, NIP jest na fakturze.")

    said = [(m.author, m.text) for m in questions.thread(item)]
    assert said == [
        ("nadawca", QUESTION),
        ("klient", "To zaliczka za remont."),
        ("nadawca", "Czy faktura jest na firmę?"),
        ("klient", "Tak, NIP jest na fakturze."),
    ]
    for page in (
        client.get(f"/d/{asked.public_token}/"),
        (
            client.force_login(user),
            client.get(reverse("requests:question-detail", args=[asked.pk])),
        )[1],
    ):
        text = _plain(page.content.decode())
        order = [text.index(part) for _, part in said[1:]]
        assert order == sorted(order)  # oldest first, nothing overwritten


@pytest.mark.django_db
def test_question_history_speaks_of_the_question(client, user, asked):
    from apps.documents.services import DocumentReviewService

    _answer(client, asked)
    item = asked.question_item
    item.refresh_from_db()
    DocumentReviewService.reject(item, "Czy faktura jest na firmę?")
    client.force_login(user)

    page = _plain(
        page_text(client.get(reverse("requests:question-detail", args=[asked.pk])))
    )

    assert "Zadano pytanie" in page and "Dopytano klienta" in page
    assert "Utworzono prośbę" not in page and "Dokument odrzucony" not in page


@pytest.mark.django_db
def test_request_page_shows_question_note_and_answer(client, user, asked):
    client.force_login(user)
    _answer(client, asked)
    client.force_login(user)

    page = _plain(
        client.get(
            reverse("requests:question-detail", args=[asked.pk])
        ).content.decode()
    )

    assert "Za co była ta płatność?" in page
    assert NOTE in page
    assert "To zaliczka za remont" in page
    assert "data-question-accept" in page and "data-question-follow-up" in page


@pytest.mark.django_db
def test_note_can_be_written_on_any_request(client, user, request_record):
    client.force_login(user)

    client.post(
        reverse("requests:note", args=[request_record.pk]),
        {"note": "Klient obiecał do piątku"},
    )

    request_record.refresh_from_db()
    assert request_record.private_note == "Klient obiecał do piątku"
    public = _plain(client.get(f"/d/{request_record.public_token}/").content.decode())
    assert "Klient obiecał do piątku" not in public


@pytest.mark.django_db
def test_note_only_on_ones_own_request(client, request_record):
    from apps.accounts.models import User

    stranger = User.objects.create_user(email="obcy@example.com", password="x")
    client.force_login(stranger)

    response = client.post(
        reverse("requests:note", args=[request_record.pk]), {"note": "hack"}
    )

    assert response.status_code == 404
    request_record.refresh_from_db()
    assert request_record.private_note == ""


@pytest.mark.django_db
def test_questions_list_tabs_and_waiting_time(client, user, client_record, asked):
    other = questions.ask(owner=user, client_id=client_record.pk, question="Drugie?")
    _answer(client, other, "Odpowiedź")
    client.force_login(user)

    waiting = _plain(page_text(client.get(reverse("requests:questions"))))
    answered = _plain(
        page_text(client.get(reverse("requests:questions") + "?tab=odpowiedziano"))
    )

    assert "Za co była ta płatność?" in waiting and "Drugie?" not in waiting
    assert "wysłane dziś" in waiting
    assert NOTE in waiting
    assert "Drugie?" in answered and "Odpowiedź" in answered
    nav = client.get(reverse("requests:questions")).content.decode()
    assert 'title="Odpowiedzi do sprawdzenia">1<' in nav


# --- the plan's limits -------------------------------------------------------------


@pytest.mark.django_db
def test_questions_dont_use_the_requests_places(user, client_record, monkeypatch):
    from apps.billing import plans, services
    from apps.requests.services import in_progress

    monkeypatch.setattr(
        services, "plan_for", lambda *args, **kwargs: (plans.FREE, "plan")
    )
    from apps.requests.services import RequestService

    for n in range(plans.FREE.active_requests):
        RequestService.create(
            owner=user,
            client_id=client_record.pk,
            name=f"Prośba {n}",
            description="",
            deadline=None,
            item_names=["Wyciąg"],
        )

    asked = questions.ask(owner=user, client_id=client_record.pk, question="Za co?")

    assert asked.question_item is not None
    assert in_progress(user).count() == plans.FREE.active_requests


@pytest.mark.django_db
def test_open_questions_have_their_own_limit(user, client_record, monkeypatch):
    from apps.billing import plans, services
    from apps.billing.services import PlanLimitError

    small = plans.Plan("t", "Test", 3, 1, 0, 0, "", open_questions=2)
    monkeypatch.setattr(services, "plan_for", lambda *args, **kwargs: (small, "plan"))
    first = questions.ask(owner=user, client_id=client_record.pk, question="Pierwsze?")
    questions.ask(owner=user, client_id=client_record.pk, question="Drugie?")

    with pytest.raises(PlanLimitError, match="2 pytań bez odpowiedzi"):
        questions.ask(owner=user, client_id=client_record.pk, question="Trzecie?")

    # An answered question frees its place.
    questions.answer(first.question_item, "Odpowiedź")
    assert questions.ask(owner=user, client_id=client_record.pk, question="Trzecie?")


@pytest.mark.django_db
def test_answer_with_a_file_is_still_told_as_an_answer(client, asked, mailoutbox):
    from apps.documents.models import Document
    from apps.notifications.inbox import notify_upload

    mailoutbox.clear()
    _answer(client, asked)
    notify_upload(
        Document.objects.create(
            request_item=asked.question_item,
            storage_key="2026/10/27/answer.pdf",
            original_filename="faktura.pdf",
            content_type="application/pdf",
            size=1024,
            checksum="a" * 64,
        )
    )
    last = Notification.objects.latest("created_at")

    assert send_pending_upload_emails(now=last.created_at.replace(year=2100)) == 1
    email = mailoutbox[-1]
    assert email.subject.startswith("Klient odpowiedział")
    body = _plain(email.body)
    assert "odpowiada na Twoje pytanie:" in body
    assert "faktura.pdf" in body


# --- questions apart from requests for documents ------------------------------


@pytest.mark.django_db
def test_questions_stay_out_of_the_requests_list_and_document_counts(
    client, user, asked, request_record, request_item
):
    client.force_login(user)

    listed = page_text(client.get(reverse("requests:list")))
    documents = page_text(
        client.get(reverse("clients:documents", args=[asked.client_id]))
    )
    stats = client.get(reverse("accounts:panel")).context

    assert request_record.name in listed
    assert asked.name not in listed
    assert "Za co była ta płatność?" not in documents
    assert stats["missing_documents"] == 1  # the document, not the question


@pytest.mark.django_db
def test_a_question_page_belongs_to_pytania(client, user, asked):
    client.force_login(user)

    html = client.get(
        reverse("requests:question-detail", args=[asked.pk])
    ).content.decode()

    assert f'href="{reverse("requests:questions")}" title="Wróć: Pytania"' in html
    assert "Zapisz jako szablon" not in html
    active = re.findall(r'class="app-nav__link is-active" href="([^"]+)"', html)
    assert active == [reverse("requests:questions")]


@pytest.mark.django_db
def test_recipient_page_lists_questions_apart_and_sits_in_a_container(
    client, asked, request_record, request_item
):
    from apps.requests.links import recipient_portal_url

    page = client.get(recipient_portal_url(asked.client.email) + "?widok=wszystkie")
    html = _plain(page.content.decode())
    questions_part, documents_part = html.split('id="received-documents"')

    assert "Pytania do Ciebie" in questions_part
    assert "Za co była ta płatność?" in questions_part
    assert "Czeka na Twoją odpowiedź" in questions_part
    assert request_record.name in documents_part
    assert "Za co była ta płatność?" not in documents_part
    assert 'class="page "' in html  # the site's container, not edge to edge
