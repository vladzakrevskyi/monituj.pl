import pytest
from django.db import IntegrityError, transaction

from apps.requests.models import PasswordProtectedAccess, RequestItem, RequestItemStatus


@pytest.mark.django_db
def test_public_token_is_generated_and_unique(user, client_record):
    from apps.requests.models import Request

    first = Request.objects.create(client=client_record, created_by=user, name="First")
    second = Request.objects.create(
        client=client_record, created_by=user, name="Second"
    )

    assert first.public_token
    assert second.public_token
    assert first.public_token != second.public_token
    assert len(first.public_token) >= 32


@pytest.mark.django_db
def test_request_is_password_protected_reflects_related_object(request_record):
    assert request_record.is_password_protected is False

    PasswordProtectedAccess.objects.create(request=request_record, password_hash="hash")
    request_record.refresh_from_db()

    assert request_record.is_password_protected is True


@pytest.mark.django_db
def test_request_item_defaults_to_brak(request_record):
    item = RequestItem.objects.create(request=request_record, name="Faktury sprzedaży")

    assert item.status == RequestItemStatus.BRAK


@pytest.mark.django_db
def test_password_protected_access_is_one_to_one(request_record):
    PasswordProtectedAccess.objects.create(
        request=request_record, password_hash="hash-one"
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PasswordProtectedAccess.objects.create(
                request=request_record, password_hash="hash-two"
            )
