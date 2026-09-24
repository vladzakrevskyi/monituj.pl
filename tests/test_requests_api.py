import json

import pytest
from django.core import mail
from django.urls import reverse

from apps.requests.services import RequestService


@pytest.mark.django_db
def test_collection_requires_login(client):
    response = client.get(reverse("requests_api:collection"))

    assert response.status_code == 401


@pytest.mark.django_db
def test_create_request_via_api(client, user, client_record):
    client.force_login(user)

    response = client.post(
        reverse("requests_api:collection"),
        data=json.dumps(
            {
                "client": client_record.pk,
                "name": "Dokumenty",
                "description": "",
                "items": ["A", "B"],
                "password": "",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["data"]["name"] == "Dokumenty"
    assert payload["data"]["total_items"] == 2
    assert payload["data"]["status"]["code"] == "brak_dokumentow"


@pytest.mark.django_db
def test_create_request_validation_error_for_empty_items(client, user, client_record):
    client.force_login(user)

    response = client.post(
        reverse("requests_api:collection"),
        data=json.dumps(
            {
                "client": client_record.pk,
                "name": "R",
                "description": "",
                "items": [],
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_detail_endpoint_requires_ownership(client, user, client_record):
    from apps.accounts.models import User

    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
    )
    other = User.objects.create_user(email="stranger@example.com", password="x")
    client.force_login(other)

    response = client.get(reverse("requests_api:detail", args=[request_obj.pk]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_create_request_via_api_creates_new_client_when_none_selected(client, user):
    from apps.clients.models import Client

    client.force_login(user)

    response = client.post(
        reverse("requests_api:collection"),
        data=json.dumps(
            {
                "new_client_name": "Nowy klient",
                "new_client_email": "nowy-api@example.com",
                "name": "Dokumenty",
                "description": "",
                "items": ["A"],
                "password": "",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 201
    new_client = Client.objects.get(email="nowy-api@example.com")
    assert new_client.owner_id == user.pk


@pytest.mark.django_db
def test_create_request_via_api_without_client_or_new_email_is_rejected(client, user):
    client.force_login(user)

    response = client.post(
        reverse("requests_api:collection"),
        data=json.dumps(
            {
                "name": "R",
                "description": "",
                "items": ["A"],
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_send_link_requires_login(client, user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
    )

    response = client.post(
        reverse("requests_api:send-link", args=[request_obj.pk]),
        data=json.dumps({"email": "ktos@example.com"}),
        content_type="application/json",
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_send_link_denies_access_to_other_owners_request(client, user, client_record):
    from apps.accounts.models import User

    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
    )
    other = User.objects.create_user(email="stranger4@example.com", password="x")
    client.force_login(other)

    response = client.post(
        reverse("requests_api:send-link", args=[request_obj.pk]),
        data=json.dumps({"email": "ktos@example.com"}),
        content_type="application/json",
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_send_link_sends_email_to_arbitrary_address(client, user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
    )
    client.force_login(user)
    mail.outbox.clear()

    response = client.post(
        reverse("requests_api:send-link", args=[request_obj.pk]),
        data=json.dumps({"email": "dowolny@example.com"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["data"]["email"] == "dowolny@example.com"
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["dowolny@example.com"]


@pytest.mark.django_db
def test_send_link_rejects_missing_email(client, user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
    )
    client.force_login(user)

    response = client.post(
        reverse("requests_api:send-link", args=[request_obj.pk]),
        data=json.dumps({"email": ""}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMAIL_REQUIRED"


@pytest.mark.django_db
def test_send_link_rejects_invalid_email(client, user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
    )
    client.force_login(user)

    response = client.post(
        reverse("requests_api:send-link", args=[request_obj.pk]),
        data=json.dumps({"email": "not-an-email"}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_EMAIL"


@pytest.mark.django_db
def test_patch_updates_request(client, user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Old",
        description="",
        deadline=None,
        item_names=["A"],
    )
    client.force_login(user)

    response = client.patch(
        reverse("requests_api:detail", args=[request_obj.pk]),
        data=json.dumps({"name": "New name", "description": ""}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["data"]["name"] == "New name"
