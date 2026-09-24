import pytest
from django.test import RequestFactory

from apps.audit.models import AuditEvent, AuditLog
from apps.common.exceptions import NotFoundAppError
from apps.requests.models import PasswordProtectedAccess
from apps.requests.services import PublicAccessService, RequestService


def _django_request():
    request = RequestFactory().get("/d/token/")
    from django.contrib.sessions.middleware import SessionMiddleware

    SessionMiddleware(lambda r: None).process_request(request)
    request.request_id = "req-public"
    return request


@pytest.mark.django_db
def test_get_by_token_returns_request(user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
    )

    found = PublicAccessService.get_by_token(request_obj.public_token)

    assert found.pk == request_obj.pk


@pytest.mark.django_db
def test_get_by_token_raises_for_unknown_token():
    with pytest.raises(NotFoundAppError):
        PublicAccessService.get_by_token("does-not-exist")


@pytest.mark.django_db
def test_unprotected_request_has_no_access_until_granted(user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
    )
    django_request = _django_request()

    assert PublicAccessService.has_access(request_obj, django_request) is False

    PublicAccessService.grant_access(request_obj, django_request)

    assert PublicAccessService.has_access(request_obj, django_request) is True


@pytest.mark.django_db
def test_protected_request_locked_until_correct_password(user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
        password="Sekretne-Haslo!1",
    )
    django_request = _django_request()

    assert PublicAccessService.has_access(request_obj, django_request) is False
    assert (
        PublicAccessService.check_password(request_obj, "wrong", django_request)
        is False
    )
    assert AuditLog.objects.filter(event=AuditEvent.PASSWORD_ACCESS_FAILED).exists()

    assert (
        PublicAccessService.check_password(
            request_obj, "Sekretne-Haslo!1", django_request
        )
        is True
    )
    assert PublicAccessService.has_access(request_obj, django_request) is True


@pytest.mark.django_db
def test_access_state_is_scoped_per_request(user, client_record):
    first = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="First",
        description="",
        deadline=None,
        item_names=["A"],
        password="Pass-One!1",
    )
    second = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Second",
        description="",
        deadline=None,
        item_names=["A"],
        password="Pass-Two!2",
    )
    django_request = _django_request()

    PublicAccessService.check_password(first, "Pass-One!1", django_request)

    assert PublicAccessService.has_access(first, django_request) is True
    assert PublicAccessService.has_access(second, django_request) is False


@pytest.mark.django_db
def test_mark_accessed_logs_public_link_access(user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="R",
        description="",
        deadline=None,
        item_names=["A"],
    )

    PublicAccessService.mark_accessed(request_obj, _django_request())

    assert AuditLog.objects.filter(
        event=AuditEvent.PUBLIC_LINK_ACCESSED, object_id=request_obj.pk
    ).exists()


@pytest.mark.django_db
def test_password_never_stored_in_plaintext_anywhere(user, client_record):
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
    assert "Sekretne-Haslo!1" not in access.password_hash
