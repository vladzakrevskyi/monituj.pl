from datetime import timedelta

import pytest
from django.contrib.auth.hashers import check_password
from django.core import mail
from django.test import RequestFactory
from django.utils import timezone

from apps.accounts.services import GuestOwnerService
from apps.audit.models import AuditEvent, AuditLog
from apps.clients.services import ClientService
from apps.common.exceptions import (
    NotFoundAppError,
    RateLimitedAppError,
    ValidationAppError,
)
from apps.notifications.models import EmailLog, EmailTemplate
from apps.requests.models import (
    AnonymousRequestThrottle,
    PasswordProtectedAccess,
    Request,
    RequestItemStatus,
)
from apps.requests.services import RequestService, RequestStatus, compute_status


def _public_django_request(remote_addr="127.0.0.1"):
    request = RequestFactory(REMOTE_ADDR=remote_addr).get("/wyslij-prosbe/")
    from django.contrib.sessions.middleware import SessionMiddleware

    SessionMiddleware(lambda r: None).process_request(request)
    request.request_id = "req-public"
    return request


@pytest.mark.django_db
def test_create_persists_request_items_and_audit_event(user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Dokumenty za wrzesien",
        description="",
        deadline=None,
        item_names=["Faktury sprzedaży", "Faktury kosztowe", ""],
    )

    assert request_obj.items.count() == 2
    assert AuditLog.objects.filter(
        event=AuditEvent.REQUEST_CREATED, object_id=request_obj.pk
    ).exists()


@pytest.mark.django_db
def test_create_sends_invitation_email_with_link_to_client(user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Dokumenty za wrzesien",
        description="",
        deadline=None,
        item_names=["Faktury sprzedaży"],
    )

    invitation_emails = [m for m in mail.outbox if m.to == [client_record.email]]
    assert len(invitation_emails) == 1
    assert request_obj.public_token in invitation_emails[0].body
    assert EmailLog.objects.filter(
        template=EmailTemplate.INVITATION,
        recipient_email=client_record.email,
        request=request_obj,
    ).exists()
    assert AuditLog.objects.filter(
        event=AuditEvent.INVITATION_SENT, object_id=request_obj.pk
    ).exists()


@pytest.mark.django_db
def test_invitation_email_shows_owner_display_name_when_set(user, client_record):
    user.display_name = "Biuro Rachunkowe Acme"
    user.save(update_fields=["display_name"])

    RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
    )

    invitation_emails = [m for m in mail.outbox if m.to == [client_record.email]]
    assert len(invitation_emails) == 1
    assert "Biuro Rachunkowe Acme" in invitation_emails[0].body


@pytest.mark.django_db
def test_create_without_password_does_not_send_password_email(user, client_record):
    RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
    )

    assert not EmailLog.objects.filter(template=EmailTemplate.ACCESS_PASSWORD).exists()


@pytest.mark.django_db
def test_create_with_password_sends_separate_password_email(user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
        password="Sekretne-Haslo!1",
    )

    password_emails = [
        m
        for m in mail.outbox
        if m.to == [client_record.email] and "Sekretne-Haslo!1" in m.body
    ]
    assert len(password_emails) == 1
    assert EmailLog.objects.filter(
        template=EmailTemplate.ACCESS_PASSWORD,
        recipient_email=client_record.email,
        request=request_obj,
    ).exists()


@pytest.mark.django_db
def test_send_invitation_can_target_an_arbitrary_email(user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
    )
    mail.outbox.clear()

    RequestService.send_invitation(request_obj, "ktokolwiek@example.com", actor=user)

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["ktokolwiek@example.com"]
    assert request_obj.public_token in mail.outbox[0].body
    assert AuditLog.objects.filter(
        event=AuditEvent.INVITATION_SENT,
        object_id=request_obj.pk,
        actor=user,
    ).exists()


@pytest.mark.django_db
def test_create_public_creates_request_owned_by_the_guest_account():
    owner = GuestOwnerService.get_or_create()
    client = ClientService.get_or_create_by_email(
        owner=owner, email="odbiorca@example.com", name="Odbiorca"
    )

    request_obj = RequestService.create_public(
        owner=owner,
        client_id=client.pk,
        name="Zadanie bez konta",
        description="",
        deadline=None,
        item_names=["A"],
        django_request=_public_django_request(),
    )

    assert request_obj.created_by_id == owner.pk
    assert request_obj.client_id == client.pk
    assert any(m.to == ["odbiorca@example.com"] for m in mail.outbox)


@pytest.mark.django_db
def test_create_public_second_request_same_day_same_ip_is_rate_limited():
    owner = GuestOwnerService.get_or_create()
    client = ClientService.get_or_create_by_email(
        owner=owner, email="odbiorca@example.com", name="Odbiorca"
    )
    RequestService.create_public(
        owner=owner,
        client_id=client.pk,
        name="Pierwsze",
        description="",
        deadline=None,
        item_names=["A"],
        django_request=_public_django_request(),
    )

    with pytest.raises(RateLimitedAppError):
        RequestService.create_public(
            owner=owner,
            client_id=client.pk,
            name="Drugie",
            description="",
            deadline=None,
            item_names=["B"],
            django_request=_public_django_request(),
        )

    assert Request.objects.filter(created_by=owner).count() == 1


@pytest.mark.django_db
def test_create_public_allows_different_ip_same_day():
    owner = GuestOwnerService.get_or_create()
    client = ClientService.get_or_create_by_email(
        owner=owner, email="odbiorca@example.com", name="Odbiorca"
    )
    RequestService.create_public(
        owner=owner,
        client_id=client.pk,
        name="Pierwsze",
        description="",
        deadline=None,
        item_names=["A"],
        django_request=_public_django_request(remote_addr="10.0.0.1"),
    )

    RequestService.create_public(
        owner=owner,
        client_id=client.pk,
        name="Drugie",
        description="",
        deadline=None,
        item_names=["B"],
        django_request=_public_django_request(remote_addr="10.0.0.2"),
    )

    assert Request.objects.filter(created_by=owner).count() == 2


@pytest.mark.django_db
def test_create_public_without_django_request_is_never_rate_limited():
    owner = GuestOwnerService.get_or_create()
    client = ClientService.get_or_create_by_email(
        owner=owner, email="odbiorca@example.com", name="Odbiorca"
    )

    RequestService.create_public(
        owner=owner,
        client_id=client.pk,
        name="A",
        description="",
        deadline=None,
        item_names=["A"],
    )
    RequestService.create_public(
        owner=owner,
        client_id=client.pk,
        name="B",
        description="",
        deadline=None,
        item_names=["A"],
    )

    assert not AnonymousRequestThrottle.objects.exists()
    assert Request.objects.filter(created_by=owner).count() == 2


@pytest.mark.django_db
def test_create_public_failed_validation_does_not_consume_daily_quota():
    owner = GuestOwnerService.get_or_create()
    client = ClientService.get_or_create_by_email(
        owner=owner, email="odbiorca@example.com", name="Odbiorca"
    )

    with pytest.raises(ValidationAppError):
        RequestService.create_public(
            owner=owner,
            client_id=client.pk,
            name="Puste",
            description="",
            deadline=None,
            item_names=["   ", ""],
            django_request=_public_django_request(),
        )

    assert not AnonymousRequestThrottle.objects.exists()

    request_obj = RequestService.create_public(
        owner=owner,
        client_id=client.pk,
        name="Poprawne",
        description="",
        deadline=None,
        item_names=["A"],
        django_request=_public_django_request(),
    )

    assert request_obj.pk is not None


@pytest.mark.django_db
def test_create_rejects_empty_item_list(user, client_record):
    with pytest.raises(ValidationAppError):
        RequestService.create(
            owner=user,
            client_id=client_record.pk,
            name="R",
            description="",
            deadline=None,
            item_names=["   ", ""],
        )
    assert Request.objects.count() == 0


@pytest.mark.django_db
def test_create_rejects_client_owned_by_someone_else(user, client_record):
    from apps.accounts.models import User

    other = User.objects.create_user(email="other@example.com", password="x")

    with pytest.raises(NotFoundAppError):
        RequestService.create(
            owner=other,
            client_id=client_record.pk,
            name="R",
            description="",
            deadline=None,
            item_names=["A"],
        )


@pytest.mark.django_db
def test_create_with_password_stores_hash_not_plaintext(user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
        password="Sekretne-Haslo!1",
    )

    access = PasswordProtectedAccess.objects.get(request=request_obj)
    assert access.password_hash != "Sekretne-Haslo!1"
    assert check_password("Sekretne-Haslo!1", access.password_hash)
    assert request_obj.is_password_protected is True


@pytest.mark.django_db
def test_get_owned_request_denies_cross_owner_access(user, client_record):
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

    with pytest.raises(NotFoundAppError):
        RequestService.get_owned_request(other, request_obj.pk)


@pytest.mark.django_db
def test_update_changes_fields_and_logs_audit(user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Old name",
        description="",
        deadline=None,
        item_names=["A"],
    )
    updated = RequestService.update(
        request_obj,
        name="New name",
        description="opis",
        deadline=None,
        reminder_settings={"max_reminders": 5},
    )

    assert updated.name == "New name"
    assert updated.max_reminders == 5
    assert AuditLog.objects.filter(
        event=AuditEvent.REQUEST_UPDATED, object_id=request_obj.pk
    ).exists()


@pytest.mark.django_db
def test_list_for_owner_status_filter(user, client_record):
    complete = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Complete",
        description="",
        deadline=None,
        item_names=["A"],
    )
    complete.items.update(status=RequestItemStatus.ZAAKCEPTOWANY)
    RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Missing",
        description="",
        deadline=None,
        item_names=["B"],
    )

    page = RequestService.list_for_owner(user, status_filter=RequestStatus.COMPLETE)

    names = [r.name for r in page.object_list]
    assert names == ["Complete"]


class _Stub:
    def __init__(self, total_items, delivered_items, deadline=None):
        self.total_items = total_items
        self.delivered_items = delivered_items
        self.deadline = deadline


def test_compute_status_missing_when_nothing_delivered():
    assert compute_status(_Stub(2, 0)) == RequestStatus.MISSING


def test_compute_status_in_progress_when_partial():
    assert compute_status(_Stub(2, 1)) == RequestStatus.IN_PROGRESS


def test_compute_status_complete_when_all_delivered():
    assert compute_status(_Stub(2, 2)) == RequestStatus.COMPLETE


def test_compute_status_overdue_when_deadline_passed_and_incomplete():
    past = timezone.now() - timedelta(days=1)
    assert compute_status(_Stub(2, 1, deadline=past)) == RequestStatus.OVERDUE


def test_compute_status_complete_overrides_overdue_deadline():
    past = timezone.now() - timedelta(days=1)
    assert compute_status(_Stub(2, 2, deadline=past)) == RequestStatus.COMPLETE
