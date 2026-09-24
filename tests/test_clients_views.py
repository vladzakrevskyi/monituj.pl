import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.clients.models import Client


@pytest.mark.django_db
def test_list_requires_login(client):
    response = client.get(reverse("clients:list"))

    assert response.status_code == 302
    assert "logowanie" in response.url


@pytest.mark.django_db
def test_list_renders_owned_clients(client, user, client_record):
    client.force_login(user)

    response = client.get(reverse("clients:list"))

    assert response.status_code == 200
    assert client_record.name.encode() in response.content


@pytest.mark.django_db
def test_list_does_not_leak_other_owners_clients(client, user):
    other = User.objects.create_user(email="stranger@example.com", password="x")
    Client.objects.create(owner=other, name="Cudzy klient", email="cudzy@example.com")
    client.force_login(user)

    response = client.get(reverse("clients:list"))

    assert b"Cudzy klient" not in response.content


@pytest.mark.django_db
def test_create_view_get_renders_form(client, user):
    client.force_login(user)

    response = client.get(reverse("clients:create"))

    assert response.status_code == 200
    assert b"Dodaj klienta" in response.content
    assert b"Nazwa klienta" in response.content
    assert b">Name<" not in response.content
    assert b">Note<" not in response.content


@pytest.mark.django_db
def test_create_view_post_creates_and_redirects(client, user):
    client.force_login(user)

    response = client.post(
        reverse("clients:create"),
        {"name": "Nowy klient", "email": "nowy@example.com", "phone": "", "note": ""},
    )

    assert response.status_code == 302
    assert response.url == reverse("clients:list")
    assert Client.objects.filter(owner=user, name="Nowy klient").exists()


@pytest.mark.django_db
def test_edit_view_get_prefills_form(client, user, client_record):
    client.force_login(user)

    response = client.get(reverse("clients:edit", args=[client_record.pk]))

    assert response.status_code == 200
    assert client_record.email.encode() in response.content


@pytest.mark.django_db
def test_edit_view_post_updates_and_redirects(client, user, client_record):
    client.force_login(user)

    response = client.post(
        reverse("clients:edit", args=[client_record.pk]),
        {
            "name": "Po edycji",
            "email": client_record.email,
            "phone": "",
            "note": "",
        },
    )

    assert response.status_code == 302
    client_record.refresh_from_db()
    assert client_record.name == "Po edycji"


@pytest.mark.django_db
def test_edit_view_404_for_other_owners_client(client, client_record):
    other = User.objects.create_user(email="stranger2@example.com", password="x")
    client.force_login(other)

    response = client.get(reverse("clients:edit", args=[client_record.pk]))

    assert response.status_code == 404
