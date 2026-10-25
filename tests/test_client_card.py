"""The client's card (/klienci/<id>/, apps/clients/card.py): what is open,
the team's notes about the client, and the client's history."""

import json

import pytest
from django.urls import reverse

from apps.clients.models import ClientNote
from apps.documents.services import UploadDocumentService
from apps.requests import questions
from tests.conftest import make_pdf_upload, page_text


def _plain(text):
    return text.replace(" ", " ")


def _card(client, client_record, **params):
    url = reverse("clients:detail", args=[client_record.pk])
    return _plain(page_text(client.get(url, params)))


@pytest.mark.django_db
def test_card_shows_what_is_open(
    client, user, client_record, request_record, request_item
):
    asked = questions.ask(
        owner=user,
        client_id=client_record.pk,
        question="Za co przelew 1 250 zł z 12.09?",
        note="VAT za wrzesień",
    )
    answered = questions.ask(
        owner=user, client_id=client_record.pk, question="Czy umowa leasingu jest nowa?"
    )
    client.get(f"/d/{answered.public_token}/")
    client.post(
        f"/api/public/{answered.public_token}/items/{answered.question_item.pk}/answer/",
        json.dumps({"answer": "Tak, od października."}),
        content_type="application/json",
    )
    client.force_login(user)

    text = _card(client, client_record)

    assert "Za co przelew 1 250 zł z 12.09?" in text and "wysłane dziś" in text
    assert "VAT za wrzesień" in text
    assert "Odpowiedź do sprawdzenia" in text and "Tak, od października." in text
    assert f"{request_record.name} - brakuje 1" in text
    assert request_item.name in text
    assert asked.pk  # still open


@pytest.mark.django_db
def test_notes_are_added_seen_by_the_team_and_never_by_the_client(
    client, user, client_record, request_record
):
    client.force_login(user)

    client.post(
        reverse("clients:note-add", args=[client_record.pk]),
        {"text": "Faktury za paliwo przynosi papierowo"},
    )

    note = ClientNote.objects.get()
    assert note.author == user
    text = _card(client, client_record)
    assert "Faktury za paliwo przynosi papierowo" in text
    assert "Dodano notatkę o kliencie" in text  # in the history too
    public = _plain(client.get(f"/d/{request_record.public_token}/").content.decode())
    assert "paliwo" not in public


@pytest.mark.django_db
def test_empty_note_is_not_saved(client, user, client_record):
    client.force_login(user)

    client.post(reverse("clients:note-add", args=[client_record.pk]), {"text": "  "})

    assert not ClientNote.objects.exists()


@pytest.mark.django_db
def test_a_note_is_deleted_by_its_author_or_the_owner_only(client, user, client_record):
    from apps.accounts.models import TeamMembership, User

    member = User.objects.create_user(email="marta@example.com", password="x")
    TeamMembership.objects.create(owner=user, user=member)
    mine = ClientNote.objects.create(client=client_record, author=user, text="Moja")
    hers = ClientNote.objects.create(client=client_record, author=member, text="Jej")

    client.force_login(member)
    session = client.session
    session["workspace"] = user.pk
    session.save()
    client.post(reverse("clients:note-delete", args=[client_record.pk, mine.pk]))
    client.post(reverse("clients:note-delete", args=[client_record.pk, hers.pk]))

    assert list(ClientNote.objects.values_list("text", flat=True)) == ["Moja"]
    client.force_login(user)
    client.post(reverse("clients:note-delete", args=[client_record.pk, mine.pk]))
    assert not ClientNote.objects.exists()


@pytest.mark.django_db
def test_history_tells_who_did_what_and_filters(
    client, user, client_record, request_record, request_item
):
    client.get(f"/d/{request_record.public_token}/")
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload("wyciag.pdf"))
    questions.ask(owner=user, client_id=client_record.pk, question="Za co przelew?")
    client.force_login(user)

    everything = _card(client, client_record)
    documents = _card(client, client_record, historia="dokumenty")
    asked = _card(client, client_record, historia="pytania")

    assert "Klient przesłał dokument" in everything and "wyciag.pdf" in everything
    assert "Klient otworzył link" in everything and "· klient" in everything
    assert "Klient przesłał dokument" in documents
    assert "Klient otworzył link" not in documents
    assert "Pytanie: Za co przelew?" in asked
    assert "wyciag.pdf" not in asked


@pytest.mark.django_db
def test_card_is_only_for_the_clients_owner(client, client_record):
    from apps.accounts.models import User

    stranger = User.objects.create_user(email="obcy@example.com", password="x")
    client.force_login(stranger)

    assert (
        client.get(reverse("clients:detail", args=[client_record.pk])).status_code
        == 404
    )
    response = client.post(
        reverse("clients:note-add", args=[client_record.pk]), {"text": "hack"}
    )
    assert response.status_code == 404
    assert not ClientNote.objects.exists()


@pytest.mark.django_db
def test_clients_list_and_request_page_lead_to_the_card(
    client, user, client_record, request_record
):
    client.force_login(user)
    card_url = reverse("clients:detail", args=[client_record.pk])

    assert card_url in client.get(reverse("clients:list")).content.decode()
    detail = client.get(reverse("requests:detail", args=[request_record.pk]))
    assert card_url in detail.content.decode()
