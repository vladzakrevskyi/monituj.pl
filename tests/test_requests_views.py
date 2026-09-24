import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.requests.models import Request
from apps.requests.services import RequestService
from tests.conftest import page_text


@pytest.mark.django_db
def test_list_requires_login(client):
    response = client.get(reverse("requests:list"))

    assert response.status_code == 302
    assert "logowanie" in response.url


@pytest.mark.django_db
def test_list_shows_owned_requests_only(client, user, client_record):
    other = User.objects.create_user(email="stranger@example.com", password="x")
    RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Moje przypomnienie",
        description="",
        deadline=None,
        item_names=["A"],
    )
    from apps.clients.models import Client

    other_client = Client.objects.create(
        owner=other, name="Cudzy", email="c@example.com"
    )
    RequestService.create(
        owner=other,
        client_id=other_client.pk,
        name="Cudze przypomnienie",
        description="",
        deadline=None,
        item_names=["A"],
    )

    client.force_login(user)
    response = client.get(reverse("requests:list"))

    assert b"Moje przypomnienie" in response.content
    assert b"Cudze przypomnienie" not in response.content


@pytest.mark.django_db
def test_create_view_creates_request_with_items(client, user, client_record):
    client.force_login(user)

    response = client.post(
        reverse("requests:create"),
        {
            "client": client_record.pk,
            "name": "Dokumenty za wrzesien",
            "description": "",
            "items": ["Faktury sprzedaży", "Faktury kosztowe", "Wyciag bankowy"],
            "password": "",
        },
    )

    request_obj = Request.objects.get(name="Dokumenty za wrzesien")
    assert response.status_code == 302
    assert response.url == reverse("requests:detail", args=[request_obj.pk])
    assert request_obj.items.count() == 3


@pytest.mark.django_db
def test_create_view_stores_deadline_as_end_of_day(client, user, client_record):
    from datetime import date, time

    from django.utils import timezone

    client.force_login(user)

    client.post(
        reverse("requests:create"),
        {
            "client": client_record.pk,
            "name": "Z terminem",
            "description": "",
            "items": ["A"],
            "password": "",
            "deadline": "2026-12-24",
        },
    )

    request_obj = Request.objects.get(name="Z terminem")
    local_deadline = timezone.localtime(request_obj.deadline)
    assert local_deadline.date() == date(2026, 12, 24)
    assert local_deadline.time() == time(23, 59, 59, 999999)


@pytest.mark.django_db
def test_create_view_without_items_shows_error_and_creates_nothing(
    client, user, client_record
):
    client.force_login(user)

    response = client.post(
        reverse("requests:create"),
        {
            "client": client_record.pk,
            "name": "Bez dokumentów",
            "description": "",
            "password": "",
        },
    )

    assert response.status_code == 200
    assert "Dodaj co najmniej jeden dokument do listy." in page_text(response)
    assert not Request.objects.filter(name="Bez dokumentów").exists()


@pytest.mark.django_db
def test_create_view_rejects_client_not_owned_by_user(client, user):
    other = User.objects.create_user(email="stranger2@example.com", password="x")
    from apps.clients.models import Client

    other_client = Client.objects.create(
        owner=other, name="Cudzy", email="c@example.com"
    )
    client.force_login(user)

    response = client.post(
        reverse("requests:create"),
        {
            "client": other_client.pk,
            "name": "R",
            "description": "",
            "items": ["A"],
            "password": "",
        },
    )

    assert response.status_code == 200
    assert not Request.objects.filter(name="R").exists()


@pytest.mark.django_db
def test_detail_view_shows_items_and_public_link(client, user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Dokumenty",
        description="",
        deadline=None,
        item_names=["Faktura A"],
    )
    client.force_login(user)

    response = client.get(reverse("requests:detail", args=[request_obj.pk]))

    assert response.status_code == 200
    assert b"Faktura A" in response.content
    assert request_obj.public_token.encode() in response.content


@pytest.mark.django_db
def test_detail_view_404_for_other_owners_request(client, user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
    )
    other = User.objects.create_user(email="stranger3@example.com", password="x")
    client.force_login(other)

    response = client.get(reverse("requests:detail", args=[request_obj.pk]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_create_view_creates_new_client_inline_when_no_existing_client_chosen(
    client, user
):
    from apps.clients.models import Client

    client.force_login(user)

    response = client.post(
        reverse("requests:create"),
        {
            "new_client_name": "Nowy klient",
            "new_client_email": "nowy-klient@example.com",
            "name": "Dokumenty dla nowego klienta",
            "description": "",
            "items": ["A"],
            "password": "",
        },
    )

    request_obj = Request.objects.get(name="Dokumenty dla nowego klienta")
    assert response.status_code == 302
    new_client = Client.objects.get(email="nowy-klient@example.com")
    assert new_client.owner_id == user.pk
    assert new_client.name == "Nowy klient"
    assert request_obj.client_id == new_client.pk


@pytest.mark.django_db
def test_create_view_without_client_or_new_client_email_shows_error(client, user):
    client.force_login(user)

    response = client.post(
        reverse("requests:create"),
        {
            "name": "R",
            "description": "",
            "items": ["A"],
            "password": "",
        },
    )

    assert response.status_code == 200
    assert (
        "Wybierz istniejącego klienta lub podaj email nowego klienta.".encode()
        in response.content
    )
    assert not Request.objects.filter(name="R").exists()


@pytest.mark.django_db
def test_edit_view_updates_metadata(client, user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Old",
        description="",
        deadline=None,
        item_names=["A"],
    )
    client.force_login(user)

    response = client.post(
        reverse("requests:edit", args=[request_obj.pk]),
        {
            "name": "Nowa nazwa",
            "description": "",
            "max_reminders": "5",
        },
    )

    assert response.status_code == 302
    request_obj.refresh_from_db()
    assert request_obj.name == "Nowa nazwa"
    assert request_obj.max_reminders == 5
