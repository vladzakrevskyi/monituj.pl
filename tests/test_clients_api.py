import json

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.clients.models import Client


@pytest.mark.django_db
def test_collection_requires_login(client):
    response = client.get(reverse("clients_api:collection"))

    assert response.status_code == 401
    assert response.json()["success"] is False


@pytest.mark.django_db
def test_create_client_via_api(client, user):
    client.force_login(user)

    response = client.post(
        reverse("clients_api:collection"),
        data=json.dumps(
            {
                "name": "Nowy klient",
                "email": "nowy@example.com",
                "phone": "",
                "note": "",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["name"] == "Nowy klient"
    assert payload["data"]["status"]["code"] == "nieaktywny"
    assert Client.objects.filter(owner=user, name="Nowy klient").exists()


@pytest.mark.django_db
def test_create_client_validation_error(client, user):
    client.force_login(user)

    response = client.post(
        reverse("clients_api:collection"),
        data=json.dumps({"name": "", "email": "not-an-email"}),
        content_type="application/json",
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_list_clients_filters_by_search(client, user):
    client.force_login(user)
    Client.objects.create(owner=user, name="Acme", email="a@example.com")
    Client.objects.create(owner=user, name="Globex", email="g@example.com")

    response = client.get(reverse("clients_api:collection"), {"q": "acme"})

    payload = response.json()
    assert payload["data"]["count"] == 1
    assert payload["data"]["results"][0]["name"] == "Acme"


@pytest.mark.django_db
def test_update_client_via_api(client, user, client_record):
    client.force_login(user)

    response = client.patch(
        reverse("clients_api:detail", args=[client_record.pk]),
        data=json.dumps(
            {
                "name": "Zaktualizowana nazwa",
                "email": client_record.email,
                "phone": "999",
                "note": "",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Zaktualizowana nazwa"


@pytest.mark.django_db
def test_delete_client_via_api(client, user, client_record):
    client.force_login(user)

    response = client.delete(reverse("clients_api:detail", args=[client_record.pk]))

    assert response.status_code == 200
    assert not Client.objects.filter(pk=client_record.pk).exists()


@pytest.mark.django_db
def test_cannot_access_other_users_client(client, client_record):
    other = User.objects.create_user(email="stranger@example.com", password="x")
    client.force_login(other)

    response = client.get(reverse("clients_api:detail", args=[client_record.pk]))

    assert response.status_code == 404
    assert response.json()["success"] is False


@pytest.mark.django_db
def test_delete_blocked_when_has_requests_returns_json_error(
    client, user, client_record
):
    from apps.requests.models import Request

    Request.objects.create(client=client_record, created_by=user, name="R")
    client.force_login(user)

    response = client.delete(reverse("clients_api:detail", args=[client_record.pk]))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CLIENT_HAS_REQUESTS"
