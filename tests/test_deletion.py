"""Deleting a request, and a client with everything sent to them: gone for
good - files in the storage included - with one count-only audit entry."""

import pytest
from django.urls import reverse

from apps.audit.models import AuditEvent, AuditLog
from apps.clients.models import Client
from apps.documents.models import Document
from apps.documents.services import UploadDocumentService
from apps.documents.storage import private_storage
from apps.requests.models import (
    RecipientAccess,
    RecurringRequest,
    Request,
    RequestItem,
)
from tests.conftest import make_pdf_upload

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def _uploaded(request_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())
    return Document.objects.get(request_item=request_item)


def _schedule(user, *clients):
    from datetime import date

    schedule = RecurringRequest.objects.create(
        owner=user,
        name="Dokumenty za {miesiąc}",
        item_names=["Faktury"],
        month_day=1,
        next_due_on=date(2026, 11, 1),
        next_run_on=date(2026, 11, 2),
    )
    schedule.clients.set(clients)
    return schedule


@pytest.mark.django_db(transaction=True)
def test_delete_a_request_with_its_files(client, user, request_record, request_item):
    document = _uploaded(request_item)
    key = document.storage_key
    assert private_storage.exists(key)
    client.force_login(user)

    response = client.post(reverse("requests:delete", args=[request_record.pk]))

    assert response.url == reverse("requests:list")
    assert not Request.objects.exists()
    assert not RequestItem.objects.exists() and not Document.objects.exists()
    assert not private_storage.exists(key)
    # The link the recipient has stops working.
    public = client.get(f"/d/{request_record.public_token}/")
    assert public.status_code == 404
    # Nothing about it is left in the log but a count.
    entry = AuditLog.objects.get(event=AuditEvent.REQUEST_DELETED)
    assert entry.metadata == {"requests": 1, "files": 1}
    assert AuditLog.objects.filter(object_id=request_record.pk).count() == 0
    # The client stays.
    assert Client.objects.filter(pk=request_record.client_id).exists()


@pytest.mark.django_db
def test_someone_elses_request_cannot_be_deleted(client, request_record):
    from apps.accounts.models import User

    other = User.objects.create_user(email="inny@example.com", password="x")
    client.force_login(other)

    response = client.post(reverse("requests:delete", args=[request_record.pk]))

    assert response.status_code == 404
    assert Request.objects.exists()


@pytest.mark.django_db
def test_deleting_needs_a_post(client, user, request_record):
    client.force_login(user)

    assert (
        client.get(reverse("requests:delete", args=[request_record.pk])).status_code
        == 405
    )
    assert Request.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_client_with_history_goes_with_everything(
    client, user, client_record, request_record, request_item
):
    other_client = Client.objects.create(owner=user, name="B", email="b@example.com")
    shared = _schedule(user, client_record, other_client)
    only_theirs = _schedule(user, client_record)
    key = _uploaded(request_item).storage_key
    RecipientAccess.objects.get_or_create(email=client_record.email)
    client.force_login(user)

    plain = client.delete(f"/api/clients/{client_record.pk}/", **AJAX)
    assert plain.status_code == 400  # without history: refused, as before
    response = client.delete(f"/api/clients/{client_record.pk}/?with_history=1", **AJAX)

    assert response.json()["data"] == {
        "deleted": True,
        "requests": 1,
        "files": 1,
        "recurring": 2,
    }
    assert not Client.objects.filter(pk=client_record.pk).exists()
    assert not Request.objects.exists() and not Document.objects.exists()
    assert not private_storage.exists(key)
    assert list(shared.clients.all()) == [other_client]
    assert not RecurringRequest.objects.filter(pk=only_theirs.pk).exists()
    assert not RecipientAccess.objects.filter(email=client_record.email).exists()
    entry = AuditLog.objects.get(event=AuditEvent.CLIENT_DELETED)
    assert entry.metadata["with_history"] is True
    assert client_record.email not in str(
        list(AuditLog.objects.values_list("metadata", flat=True))
    )


@pytest.mark.django_db
def test_received_list_still_needs_login(client):
    response = client.get(reverse("requests:received"))

    assert response.status_code == 302 and "logowanie" in response.url


def _request(user, client_record, name):
    request_obj = Request.objects.create(
        client=client_record, created_by=user, name=name
    )
    request_obj.items.create(name="Faktury")
    return request_obj


@pytest.mark.django_db
def test_delete_a_request_and_its_client(client, user, client_record):
    first = _request(user, client_record, "Wrzesień")
    _request(user, client_record, "Październik")
    other = Client.objects.create(owner=user, name="B", email="b@example.com")
    kept = _request(user, other, "Inny klient")
    client.force_login(user)

    client.post(reverse("requests:delete", args=[first.pk]), {"with_client": "1"})

    assert not Client.objects.filter(pk=client_record.pk).exists()
    assert list(Request.objects.all()) == [kept]


@pytest.mark.django_db
def test_bulk_delete_ticked_rows_only_own(client, user, client_record):
    a = _request(user, client_record, "A")
    b = _request(user, client_record, "B")
    c = _request(user, client_record, "C")
    from apps.accounts.models import User

    stranger = User.objects.create_user(email="obcy@example.com", password="x")
    foreign_client = Client.objects.create(
        owner=stranger, name="X", email="x@example.com"
    )
    foreign = _request(stranger, foreign_client, "Cudza")
    client.force_login(user)

    response = client.post(
        reverse("requests:bulk-delete"), {"ids": [a.pk, b.pk, foreign.pk]}
    )

    assert response.url == reverse("requests:list")
    assert set(Request.objects.all()) == {c, foreign}
    assert Client.objects.filter(pk=client_record.pk).exists()


@pytest.mark.django_db
def test_bulk_delete_everything_matching_the_filters(client, user, client_record):
    for number in range(25):
        _request(user, client_record, f"Faktury {number}")
    other = _request(user, client_record, "Umowy")
    client.force_login(user)

    response = client.post(
        reverse("requests:bulk-delete"), {"all": "1", "q": "Faktury"}
    )

    assert list(Request.objects.all()) == [other]
    # Back to the same filtered list.
    assert response.url == reverse("requests:list") + "?q=Faktury"


@pytest.mark.django_db
def test_bulk_delete_with_clients(client, user, client_record):
    a = _request(user, client_record, "A")
    _request(user, client_record, "Niezaznaczona")
    other = Client.objects.create(owner=user, name="B", email="b@example.com")
    kept = _request(user, other, "Zostaje")
    client.force_login(user)

    client.post(reverse("requests:bulk-delete"), {"ids": [a.pk], "with_clients": "1"})

    assert list(Request.objects.all()) == [kept]
    assert list(Client.objects.filter(owner=user)) == [other]


@pytest.mark.django_db
def test_bulk_delete_with_nothing_ticked(client, user, client_record):
    _request(user, client_record, "A")
    client.force_login(user)

    client.post(reverse("requests:bulk-delete"), {})

    assert Request.objects.count() == 1


@pytest.mark.django_db
def test_list_has_row_checkboxes_and_the_bulk_bar(client, user, client_record):
    request_obj = _request(user, client_record, "A")
    client.force_login(user)

    html = client.get(reverse("requests:list"), {"q": "A"}).content.decode()

    assert f'name="ids" value="{request_obj.pk}" form="bulk-form"' in html
    assert '<input type="hidden" name="q" value="A">' in html
    assert "data-bulk-clear" in html


# --- clients in bulk ------------------------------------------------------------


@pytest.mark.django_db
def test_bulk_delete_clients_with_their_requests(client, user, client_record):
    _request(user, client_record, "A")
    empty = Client.objects.create(owner=user, name="Bez próśb", email="e@example.com")
    kept = Client.objects.create(owner=user, name="Zostaje", email="z@example.com")
    kept_request = _request(user, kept, "Zostaje")
    from apps.accounts.models import User

    stranger = User.objects.create_user(email="obcy@example.com", password="x")
    foreign = Client.objects.create(owner=stranger, name="X", email="x@example.com")
    client.force_login(user)

    response = client.post(
        reverse("clients:bulk-delete"),
        {"ids": [client_record.pk, empty.pk, foreign.pk]},
    )

    assert response.url == reverse("clients:list")
    assert set(Client.objects.all()) == {kept, foreign}
    assert list(Request.objects.all()) == [kept_request]


@pytest.mark.django_db
def test_bulk_delete_every_client_matching_the_search(client, user):
    for number in range(25):
        Client.objects.create(
            owner=user, name=f"Kowalski {number}", email=f"k{number}@example.com"
        )
    other = Client.objects.create(owner=user, name="Nowak", email="n@example.com")
    client.force_login(user)

    response = client.post(
        reverse("clients:bulk-delete"), {"all": "1", "q": "Kowalski"}
    )

    assert list(Client.objects.all()) == [other]
    assert response.url == reverse("clients:list") + "?q=Kowalski"


@pytest.mark.django_db
def test_client_list_has_row_checkboxes(client, user, client_record):
    client.force_login(user)

    html = client.get(reverse("clients:list")).content.decode()

    assert f'name="ids" value="{client_record.pk}" form="bulk-form"' in html
    assert 'action="/klienci/usun/"' in html
