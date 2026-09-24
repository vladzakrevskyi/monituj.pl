import pytest

from apps.accounts.models import User
from apps.accounts.services import GUEST_OWNER_EMAIL, GuestOwnerService


@pytest.mark.django_db
def test_get_or_create_creates_an_unusable_inactive_account():
    owner = GuestOwnerService.get_or_create()

    assert owner.email == GUEST_OWNER_EMAIL
    assert owner.is_active is False
    assert owner.has_usable_password() is False


@pytest.mark.django_db
def test_get_or_create_returns_the_same_account_on_repeated_calls():
    first = GuestOwnerService.get_or_create()
    second = GuestOwnerService.get_or_create()

    assert first.pk == second.pk
    assert User.objects.filter(email=GUEST_OWNER_EMAIL).count() == 1
