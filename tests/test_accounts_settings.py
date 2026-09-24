from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.models import AccountToken, AccountTokenPurpose, User
from apps.accounts.services import (
    EmailChangeService,
    PasswordChangeService,
    ProfileService,
)
from apps.audit.models import AuditEvent, AuditLog
from apps.common.exceptions import ValidationAppError
from apps.common.security import generate_public_token, hash_token

VALID_PASSWORD = "Sup3r-Secret-Pass!23"


@pytest.fixture
def settings_user(db):
    return User.objects.create_user(
        email="settings-user@example.com", password=VALID_PASSWORD
    )


def _reuse_pending_token(user, purpose):
    """Tokens are only ever handed out inside an email body; tests swap in a
    known raw token so they can drive the confirm step deterministically,
    mirroring the pattern already used for PasswordResetService tests."""
    token = AccountToken.objects.get(user=user, purpose=purpose, used_at__isnull=True)
    raw_token = generate_public_token()
    token.token_hash = hash_token(raw_token)
    token.save(update_fields=["token_hash"])
    return raw_token


@pytest.mark.django_db
def test_update_profile_saves_display_name_and_logs_audit(settings_user):
    ProfileService.update_profile(settings_user, "  Acme Sp. z o.o.  ")

    settings_user.refresh_from_db()
    assert settings_user.display_name == "Acme Sp. z o.o."
    assert AuditLog.objects.filter(
        actor=settings_user, event=AuditEvent.PROFILE_UPDATED
    ).exists()


@pytest.mark.django_db
def test_password_change_request_rejects_wrong_current_password(settings_user):
    with pytest.raises(ValidationAppError) as exc_info:
        PasswordChangeService.request_change(
            settings_user, "wrong-password", "Nowe-Bezpieczne-Haslo!1"
        )

    assert exc_info.value.code == "INVALID_CURRENT_PASSWORD"
    assert not AccountToken.objects.exists()


@pytest.mark.django_db
def test_password_change_request_rejects_weak_new_password(settings_user):
    with pytest.raises(ValidationAppError):
        PasswordChangeService.request_change(settings_user, VALID_PASSWORD, "123")

    assert not AccountToken.objects.exists()


@pytest.mark.django_db
def test_password_change_request_sends_confirmation_email_not_password_yet(
    settings_user,
):
    PasswordChangeService.request_change(
        settings_user, VALID_PASSWORD, "Nowe-Bezpieczne-Haslo!1"
    )

    settings_user.refresh_from_db()
    assert settings_user.check_password(VALID_PASSWORD)
    assert not settings_user.check_password("Nowe-Bezpieczne-Haslo!1")
    assert len(mail.outbox) == 1
    assert AccountToken.objects.filter(
        user=settings_user, purpose=AccountTokenPurpose.PASSWORD_CHANGE
    ).exists()
    assert AuditLog.objects.filter(
        actor=settings_user, event=AuditEvent.PASSWORD_CHANGE_REQUESTED
    ).exists()


@pytest.mark.django_db
def test_password_change_confirm_applies_new_password_and_notifies(settings_user):
    PasswordChangeService.request_change(
        settings_user, VALID_PASSWORD, "Nowe-Bezpieczne-Haslo!1"
    )
    raw_token = _reuse_pending_token(settings_user, AccountTokenPurpose.PASSWORD_CHANGE)
    mail.outbox.clear()

    PasswordChangeService.confirm_change(raw_token)

    settings_user.refresh_from_db()
    assert settings_user.check_password("Nowe-Bezpieczne-Haslo!1")
    assert not settings_user.check_password(VALID_PASSWORD)
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [settings_user.email]
    assert AuditLog.objects.filter(
        actor=settings_user, event=AuditEvent.PASSWORD_CHANGED
    ).exists()


@pytest.mark.django_db
def test_password_change_confirm_rejects_invalid_token(settings_user):
    with pytest.raises(ValidationAppError) as exc_info:
        PasswordChangeService.confirm_change("not-a-real-token")

    assert exc_info.value.code == "INVALID_TOKEN"


@pytest.mark.django_db
def test_password_change_confirm_rejects_expired_token(settings_user):
    PasswordChangeService.request_change(
        settings_user, VALID_PASSWORD, "Nowe-Bezpieczne-Haslo!1"
    )
    token = AccountToken.objects.get(
        user=settings_user, purpose=AccountTokenPurpose.PASSWORD_CHANGE
    )
    raw_token = generate_public_token()
    token.token_hash = hash_token(raw_token)
    token.expires_at = timezone.now() - timedelta(minutes=1)
    token.save(update_fields=["token_hash", "expires_at"])

    with pytest.raises(ValidationAppError):
        PasswordChangeService.confirm_change(raw_token)

    settings_user.refresh_from_db()
    assert settings_user.check_password(VALID_PASSWORD)


@pytest.mark.django_db
def test_password_change_confirm_invalidates_other_outstanding_tokens(settings_user):
    PasswordChangeService.request_change(
        settings_user, VALID_PASSWORD, "Pierwsze-Haslo!11"
    )
    first_token = AccountToken.objects.get(
        user=settings_user, purpose=AccountTokenPurpose.PASSWORD_CHANGE
    )
    first_raw = generate_public_token()
    first_token.token_hash = hash_token(first_raw)
    first_token.save(update_fields=["token_hash"])

    settings_user.refresh_from_db()
    PasswordChangeService.request_change(
        settings_user, VALID_PASSWORD, "Drugie-Haslo!222"
    )
    second_token = (
        AccountToken.objects.filter(
            user=settings_user,
            purpose=AccountTokenPurpose.PASSWORD_CHANGE,
            used_at__isnull=True,
        )
        .exclude(pk=first_token.pk)
        .get()
    )
    second_raw = generate_public_token()
    second_token.token_hash = hash_token(second_raw)
    second_token.save(update_fields=["token_hash"])

    PasswordChangeService.confirm_change(second_raw)

    with pytest.raises(ValidationAppError):
        PasswordChangeService.confirm_change(first_raw)


@pytest.mark.django_db
def test_email_change_request_rejects_wrong_current_password(settings_user):
    with pytest.raises(ValidationAppError) as exc_info:
        EmailChangeService.request_change(
            settings_user, "new@example.com", "wrong-password"
        )

    assert exc_info.value.code == "INVALID_CURRENT_PASSWORD"


@pytest.mark.django_db
def test_email_change_request_rejects_already_taken_email(settings_user):
    User.objects.create_user(email="taken@example.com", password=VALID_PASSWORD)

    with pytest.raises(ValidationAppError) as exc_info:
        EmailChangeService.request_change(
            settings_user, "taken@example.com", VALID_PASSWORD
        )

    assert exc_info.value.code == "EMAIL_TAKEN"


@pytest.mark.django_db
def test_email_change_request_rejects_same_as_current_email(settings_user):
    with pytest.raises(ValidationAppError) as exc_info:
        EmailChangeService.request_change(
            settings_user, settings_user.email.upper(), VALID_PASSWORD
        )

    assert exc_info.value.code == "EMAIL_UNCHANGED"


@pytest.mark.django_db
def test_email_change_request_notifies_old_and_new_address(settings_user):
    EmailChangeService.request_change(settings_user, "nowy@example.com", VALID_PASSWORD)

    settings_user.refresh_from_db()
    assert settings_user.email == "settings-user@example.com"
    assert len(mail.outbox) == 2
    recipients = {tuple(m.to) for m in mail.outbox}
    assert recipients == {("nowy@example.com",), ("settings-user@example.com",)}
    assert AuditLog.objects.filter(
        actor=settings_user, event=AuditEvent.EMAIL_CHANGE_REQUESTED
    ).exists()


@pytest.mark.django_db
def test_email_change_confirm_applies_new_email_and_notifies_old_address(
    settings_user,
):
    old_email = settings_user.email
    EmailChangeService.request_change(settings_user, "nowy@example.com", VALID_PASSWORD)
    raw_token = _reuse_pending_token(settings_user, AccountTokenPurpose.EMAIL_CHANGE)
    mail.outbox.clear()

    EmailChangeService.confirm_change(raw_token)

    settings_user.refresh_from_db()
    assert settings_user.email == "nowy@example.com"
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [old_email]
    assert AuditLog.objects.filter(
        actor=settings_user, event=AuditEvent.EMAIL_CHANGED
    ).exists()


@pytest.mark.django_db
def test_email_change_confirm_rechecks_uniqueness_to_close_race_condition(
    settings_user,
):
    """The target email could be taken by someone else between request and
    confirm time; confirming must re-check, not just trust the pending
    token."""
    EmailChangeService.request_change(
        settings_user, "raced@example.com", VALID_PASSWORD
    )
    raw_token = _reuse_pending_token(settings_user, AccountTokenPurpose.EMAIL_CHANGE)
    User.objects.create_user(email="raced@example.com", password=VALID_PASSWORD)

    with pytest.raises(ValidationAppError) as exc_info:
        EmailChangeService.confirm_change(raw_token)

    assert exc_info.value.code == "EMAIL_TAKEN"
    settings_user.refresh_from_db()
    assert settings_user.email != "raced@example.com"


@pytest.mark.django_db
def test_email_change_confirm_rejects_invalid_token():
    with pytest.raises(ValidationAppError) as exc_info:
        EmailChangeService.confirm_change("not-a-real-token")

    assert exc_info.value.code == "INVALID_TOKEN"
