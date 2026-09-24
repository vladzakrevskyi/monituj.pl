import pytest

from apps.audit.models import AuditEvent, AuditLog
from apps.clients.models import Client
from apps.clients.services import ClientService, ClientStatus, compute_status
from apps.common.exceptions import NotFoundAppError, ValidationAppError
from apps.requests.models import Request, RequestItem, RequestItemStatus


@pytest.mark.django_db
def test_create_logs_audit_event(user):
    client = ClientService.create(owner=user, name="Nowy klient", email="n@example.com")

    assert client.pk is not None
    assert AuditLog.objects.filter(
        actor=user, event=AuditEvent.CLIENT_CREATED, object_id=client.pk
    ).exists()


@pytest.mark.django_db
def test_update_logs_audit_event(client_record):
    ClientService.update(
        client_record, name="Nowa nazwa", email="new@example.com", phone="123"
    )
    client_record.refresh_from_db()

    assert client_record.name == "Nowa nazwa"
    assert client_record.phone == "123"
    assert AuditLog.objects.filter(
        event=AuditEvent.CLIENT_UPDATED, object_id=client_record.pk
    ).exists()


@pytest.mark.django_db
def test_delete_succeeds_without_requests(client_record):
    client_id = client_record.pk

    ClientService.delete(client_record)

    assert not Client.objects.filter(pk=client_id).exists()
    assert AuditLog.objects.filter(
        event=AuditEvent.CLIENT_DELETED, object_id=client_id
    ).exists()


@pytest.mark.django_db
def test_delete_blocked_when_client_has_requests(client_record, user):
    Request.objects.create(client=client_record, created_by=user, name="Dokumenty")

    with pytest.raises(ValidationAppError):
        ClientService.delete(client_record)

    assert Client.objects.filter(pk=client_record.pk).exists()


@pytest.mark.django_db
def test_get_owned_client_denies_cross_owner_access(client_record):
    from apps.accounts.models import User

    other_owner = User.objects.create_user(email="other@example.com", password="x")

    with pytest.raises(NotFoundAppError):
        ClientService.get_owned_client(other_owner, client_record.pk)


@pytest.mark.django_db
def test_list_for_owner_search_matches_name_or_email(user):
    ClientService.create(owner=user, name="Acme Sp.", email="contact@acme.example")
    ClientService.create(owner=user, name="Globex", email="hello@globex.example")

    page = ClientService.list_for_owner(user, search="acme")

    names = [c.name for c in page.object_list]
    assert names == ["Acme Sp."]


@pytest.mark.django_db
def test_compute_status_inactive_when_no_requests(client_record):
    page = ClientService.list_for_owner(client_record.owner)
    client = page.object_list[0]

    assert compute_status(client) == ClientStatus.INACTIVE


@pytest.mark.django_db
def test_compute_status_missing_when_nothing_delivered(client_record, user):
    request = Request.objects.create(client=client_record, created_by=user, name="R")
    RequestItem.objects.create(
        request=request, name="Faktura", status=RequestItemStatus.BRAK
    )

    page = ClientService.list_for_owner(user)
    client = page.object_list[0]

    assert compute_status(client) == ClientStatus.MISSING_DOCUMENTS


@pytest.mark.django_db
def test_compute_status_active_when_partially_delivered(client_record, user):
    request = Request.objects.create(client=client_record, created_by=user, name="R")
    RequestItem.objects.create(
        request=request, name="A", status=RequestItemStatus.DOSTARCZONY
    )
    RequestItem.objects.create(request=request, name="B", status=RequestItemStatus.BRAK)

    page = ClientService.list_for_owner(user)
    client = page.object_list[0]

    assert compute_status(client) == ClientStatus.ACTIVE


@pytest.mark.django_db
def test_compute_status_all_delivered(client_record, user):
    request = Request.objects.create(client=client_record, created_by=user, name="R")
    RequestItem.objects.create(
        request=request, name="A", status=RequestItemStatus.ZAAKCEPTOWANY
    )

    page = ClientService.list_for_owner(user)
    client = page.object_list[0]

    assert compute_status(client) == ClientStatus.ALL_DELIVERED


@pytest.mark.django_db
def test_get_or_create_by_email_creates_new_client(user):
    client = ClientService.get_or_create_by_email(
        owner=user, email="nowy@example.com", name="Nowy klient"
    )

    assert client.pk is not None
    assert client.name == "Nowy klient"
    assert client.email == "nowy@example.com"
    assert AuditLog.objects.filter(
        event=AuditEvent.CLIENT_CREATED, object_id=client.pk
    ).exists()


@pytest.mark.django_db
def test_get_or_create_by_email_falls_back_to_email_local_part_when_name_blank(user):
    client = ClientService.get_or_create_by_email(
        owner=user, email="janek@example.com", name=""
    )

    assert client.name == "janek"


@pytest.mark.django_db
def test_get_or_create_by_email_returns_existing_client_case_insensitively(
    user, client_record
):
    client = ClientService.get_or_create_by_email(
        owner=user, email=client_record.email.upper(), name="Inna nazwa"
    )

    assert client.pk == client_record.pk
    assert client.name == client_record.name


@pytest.mark.django_db
def test_get_or_create_by_email_does_not_match_other_owners_client(user, client_record):
    from apps.accounts.models import User

    other = User.objects.create_user(email="other-owner@example.com", password="x")

    client = ClientService.get_or_create_by_email(
        owner=other, email=client_record.email, name=""
    )

    assert client.pk != client_record.pk
    assert client.owner_id == other.pk
