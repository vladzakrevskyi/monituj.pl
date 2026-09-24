import pytest
from django.core import mail
from django.urls import reverse

from apps.accounts.services import GUEST_OWNER_EMAIL
from apps.audit.models import AuditEvent, AuditLog
from apps.clients.models import Client
from apps.requests.models import Request
from apps.requests.services import RequestService
from tests.conftest import page_text


@pytest.mark.django_db
def test_public_view_shows_checklist_for_unprotected_request(
    client, user, client_record
):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Dokumenty za wrzesien",
        description="",
        deadline=None,
        item_names=["Faktury sprzedaży", "Faktury kosztowe"],
    )

    response = client.get(
        reverse("public:request-detail", args=[request_obj.public_token])
    )

    assert response.status_code == 200
    assert "Faktury sprzedaży".encode() in response.content
    assert AuditLog.objects.filter(
        event=AuditEvent.PUBLIC_LINK_ACCESSED, object_id=request_obj.pk
    ).exists()


@pytest.mark.django_db
def test_public_view_shows_owner_display_name_when_set(client, user, client_record):
    user.display_name = "Biuro Rachunkowe Acme"
    user.save(update_fields=["display_name"])
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
    )

    response = client.get(
        reverse("public:request-detail", args=[request_obj.public_token])
    )

    assert b"Biuro Rachunkowe Acme" in response.content


@pytest.mark.django_db
def test_public_view_404_for_unknown_token(client):
    response = client.get(reverse("public:request-detail", args=["does-not-exist"]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_public_view_does_not_leak_other_requests_or_owner_info(
    client, user, client_record
):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
    )

    response = client.get(
        reverse("public:request-detail", args=[request_obj.public_token])
    )

    assert user.email.encode() not in response.content
    assert client_record.email.encode() not in response.content


@pytest.mark.django_db
def test_public_view_shows_password_gate_for_protected_request(
    client, user, client_record
):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
        password="Sekretne-Haslo!1",
    )

    response = client.get(
        reverse("public:request-detail", args=[request_obj.public_token])
    )

    assert response.status_code == 200
    assert "zabezpieczony hasłem".encode() in response.content
    assert b"Faktury" not in response.content


@pytest.mark.django_db
def test_public_view_unlocks_with_correct_password(client, user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["Faktura testowa"],
        password="Sekretne-Haslo!1",
    )
    url = reverse("public:request-detail", args=[request_obj.public_token])

    response = client.post(url, {"password": "Sekretne-Haslo!1"}, follow=True)

    assert response.status_code == 200
    assert b"Faktura testowa" in response.content


@pytest.mark.django_db
def test_public_view_rejects_wrong_password(client, user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
        password="Sekretne-Haslo!1",
    )
    url = reverse("public:request-detail", args=[request_obj.public_token])

    response = client.post(url, {"password": "wrong"})

    assert response.status_code == 200
    assert "Nieprawidłowe hasło".encode() in response.content
    assert AuditLog.objects.filter(event=AuditEvent.PASSWORD_ACCESS_FAILED).exists()


@pytest.mark.django_db
def test_guest_request_create_get_renders_form(client):
    response = client.get(reverse("public:guest-request-create"))

    assert response.status_code == 200
    assert "Wyślij prośbę o dokumenty" in page_text(response)


@pytest.mark.django_db
def test_guest_request_create_creates_request_and_sends_invitation(client):
    response = client.post(
        reverse("public:guest-request-create"),
        {
            "client_name": "Odbiorca Sp. z o.o.",
            "client_email": "odbiorca@example.com",
            "name": "Dokumenty na koniec miesiaca",
            "description": "",
            "items": ["Faktura VAT"],
            "password": "",
            "accept_terms": "on",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert b"Zadanie utworzone" in response.content

    request_obj = Request.objects.get(name="Dokumenty na koniec miesiaca")
    assert request_obj.created_by.email == GUEST_OWNER_EMAIL
    assert Client.objects.filter(
        owner=request_obj.created_by, email="odbiorca@example.com"
    ).exists()
    assert any(m.to == ["odbiorca@example.com"] for m in mail.outbox)


@pytest.mark.django_db
def test_guest_request_create_with_password_sends_password_email(client):
    client.post(
        reverse("public:guest-request-create"),
        {
            "client_name": "Odbiorca",
            "client_email": "odbiorca-pw@example.com",
            "name": "Zadanie z hasłem",
            "description": "",
            "items": ["A"],
            "password": "Sekretne-Haslo!1",
            "accept_terms": "on",
        },
    )

    request_obj = Request.objects.get(name="Zadanie z hasłem")
    assert request_obj.is_password_protected is True
    password_emails = [
        m
        for m in mail.outbox
        if m.to == ["odbiorca-pw@example.com"] and "Sekretne-Haslo!1" in m.body
    ]
    assert len(password_emails) == 1


@pytest.mark.django_db
def test_guest_request_create_without_items_shows_error(client):
    response = client.post(
        reverse("public:guest-request-create"),
        {
            "client_name": "Odbiorca",
            "client_email": "odbiorca@example.com",
            "name": "Bez dokumentów",
            "description": "",
            "password": "",
            "accept_terms": "on",
        },
    )

    assert response.status_code == 200
    assert "Dodaj co najmniej jeden dokument do listy." in page_text(response)
    assert not Request.objects.filter(name="Bez dokumentów").exists()


@pytest.mark.django_db
def test_guest_request_create_requires_client_name_and_email(client):
    response = client.post(
        reverse("public:guest-request-create"),
        {"name": "R", "description": "", "items": ["A"], "password": ""},
    )

    assert response.status_code == 200
    assert not Request.objects.filter(name="R").exists()


@pytest.mark.django_db
def test_guest_request_create_second_submission_same_day_is_blocked(client):
    client.post(
        reverse("public:guest-request-create"),
        {
            "client_name": "Pierwszy",
            "client_email": "pierwszy@example.com",
            "name": "Pierwsze",
            "description": "",
            "items": ["A"],
            "password": "",
            "accept_terms": "on",
        },
    )

    response = client.post(
        reverse("public:guest-request-create"),
        {
            "client_name": "Drugi",
            "client_email": "drugi@example.com",
            "name": "Drugie",
            "description": "",
            "items": ["B"],
            "password": "",
            "accept_terms": "on",
        },
    )

    assert response.status_code == 200
    assert (
        "Dzisiaj można utworzyć tylko jedno zadanie bez konta".encode()
        in response.content
    )
    assert not Request.objects.filter(name="Drugie").exists()


@pytest.mark.django_db
def test_guest_request_create_second_submission_blocked_even_in_a_fresh_session(
    client,
):
    """A brand-new test client has no cookies at all - equivalent to a fresh
    incognito window. The daily limit must still hold because it's keyed by
    IP, not by any client-side state."""
    from django.test import Client as TestClient

    client.post(
        reverse("public:guest-request-create"),
        {
            "client_name": "Pierwszy",
            "client_email": "pierwszy@example.com",
            "name": "Pierwsze",
            "description": "",
            "items": ["A"],
            "password": "",
            "accept_terms": "on",
        },
    )

    incognito_client = TestClient()
    response = incognito_client.post(
        reverse("public:guest-request-create"),
        {
            "client_name": "Drugi",
            "client_email": "drugi@example.com",
            "name": "Drugie",
            "description": "",
            "items": ["B"],
            "password": "",
            "accept_terms": "on",
        },
    )

    assert response.status_code == 200
    assert (
        "Dzisiaj można utworzyć tylko jedno zadanie bez konta".encode()
        in response.content
    )
    assert not Request.objects.filter(name="Drugie").exists()
