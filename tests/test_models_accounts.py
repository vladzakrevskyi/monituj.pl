from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.accounts.models import AccountToken, AccountTokenPurpose, User


@pytest.mark.django_db
def test_create_user_hashes_password():
    user = User.objects.create_user(email="a@example.com", password="s3cr3t-pass!")

    assert user.password != "s3cr3t-pass!"
    assert user.check_password("s3cr3t-pass!")


@pytest.mark.django_db
def test_user_email_is_unique():
    User.objects.create_user(email="dup@example.com", password="s3cr3t-pass!")

    with pytest.raises(IntegrityError):
        User.objects.create_user(email="dup@example.com", password="other-pass!")


@pytest.mark.django_db
def test_is_email_verified_reflects_timestamp():
    user = User.objects.create_user(email="b@example.com", password="s3cr3t-pass!")
    assert user.is_email_verified is False

    user.email_verified_at = timezone.now()
    assert user.is_email_verified is True


@pytest.mark.django_db
def test_account_token_is_valid_only_when_unused_and_unexpired(user):
    valid_token = AccountToken.objects.create(
        user=user,
        purpose=AccountTokenPurpose.EMAIL_VERIFICATION,
        token_hash="a" * 64,
        expires_at=timezone.now() + timedelta(hours=1),
    )
    expired_token = AccountToken.objects.create(
        user=user,
        purpose=AccountTokenPurpose.EMAIL_VERIFICATION,
        token_hash="b" * 64,
        expires_at=timezone.now() - timedelta(hours=1),
    )
    used_token = AccountToken.objects.create(
        user=user,
        purpose=AccountTokenPurpose.PASSWORD_RESET,
        token_hash="c" * 64,
        expires_at=timezone.now() + timedelta(hours=1),
        used_at=timezone.now(),
    )

    assert valid_token.is_valid is True
    assert expired_token.is_valid is False
    assert used_token.is_valid is False
