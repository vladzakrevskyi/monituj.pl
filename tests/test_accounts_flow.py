from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.models import AccountToken, AccountTokenPurpose, User
from apps.accounts.services import (
    AuthenticationService,
    PasswordResetService,
    RegistrationService,
    VerificationService,
)
from apps.audit.models import AuditEvent, AuditLog
from apps.common.exceptions import ValidationAppError
from apps.common.security import generate_public_token, hash_token
from apps.notifications.models import EmailLog, EmailStatus

VALID_PASSWORD = "Sup3r-Secret-Pass!23"


@pytest.mark.django_db
def test_register_creates_user_sends_verification_and_logs_audit():
    user = RegistrationService.register(
        email="new@example.com",
        password=VALID_PASSWORD,
        accept_terms=True,
        accept_privacy_policy=True,
    )

    assert user.pk is not None
    assert user.is_email_verified is False
    assert user.terms_accepted_at is not None
    assert user.privacy_policy_accepted_at is not None

    assert AccountToken.objects.filter(
        user=user, purpose=AccountTokenPurpose.EMAIL_VERIFICATION
    ).exists()
    assert EmailLog.objects.filter(
        recipient_email=user.email, status=EmailStatus.SENT
    ).exists()
    assert len(mail.outbox) == 1
    assert "weryfikacja-email" in mail.outbox[0].body
    assert AuditLog.objects.filter(
        actor=user, event=AuditEvent.USER_REGISTERED
    ).exists()


@pytest.mark.django_db
def test_register_rejects_duplicate_email():
    RegistrationService.register(
        email="dup@example.com",
        password=VALID_PASSWORD,
        accept_terms=True,
        accept_privacy_policy=True,
    )

    with pytest.raises(ValidationAppError):
        RegistrationService.register(
            email="dup@example.com",
            password=VALID_PASSWORD,
            accept_terms=True,
            accept_privacy_policy=True,
        )


@pytest.mark.django_db
def test_register_rejects_weak_password():
    with pytest.raises(ValidationAppError):
        RegistrationService.register(
            email="weak@example.com",
            password="12345",
            accept_terms=True,
            accept_privacy_policy=True,
        )


@pytest.mark.django_db
def test_register_requires_consent():
    with pytest.raises(ValidationAppError):
        RegistrationService.register(
            email="noconsent@example.com",
            password=VALID_PASSWORD,
            accept_terms=False,
            accept_privacy_policy=True,
        )


@pytest.mark.django_db
def test_verify_email_marks_user_verified_and_token_single_use():
    user = User.objects.create_user(email="verify@example.com", password=VALID_PASSWORD)
    raw_token = generate_public_token()
    AccountToken.objects.create(
        user=user,
        purpose=AccountTokenPurpose.EMAIL_VERIFICATION,
        token_hash=hash_token(raw_token),
        expires_at=timezone.now() + timedelta(hours=1),
    )

    VerificationService.verify(raw_token)
    user.refresh_from_db()
    assert user.is_email_verified is True

    with pytest.raises(ValidationAppError):
        VerificationService.verify(raw_token)


@pytest.mark.django_db
def test_verify_email_rejects_expired_token():
    user = User.objects.create_user(
        email="expired@example.com", password=VALID_PASSWORD
    )
    raw_token = generate_public_token()
    AccountToken.objects.create(
        user=user,
        purpose=AccountTokenPurpose.EMAIL_VERIFICATION,
        token_hash=hash_token(raw_token),
        expires_at=timezone.now() - timedelta(hours=1),
    )

    with pytest.raises(ValidationAppError):
        VerificationService.verify(raw_token)


@pytest.mark.django_db
def test_login_succeeds_with_correct_credentials(rf):
    User.objects.create_user(email="login@example.com", password=VALID_PASSWORD)
    request = rf.post("/logowanie/")
    request.request_id = "req-1"

    from django.contrib.sessions.middleware import SessionMiddleware

    SessionMiddleware(lambda r: None).process_request(request)

    user = AuthenticationService.login(request, "login@example.com", VALID_PASSWORD)

    assert user.email == "login@example.com"
    assert AuditLog.objects.filter(actor=user, event=AuditEvent.USER_LOGIN).exists()


@pytest.mark.django_db
def test_login_fails_with_wrong_password_and_does_not_reveal_which_field(rf):
    User.objects.create_user(email="login2@example.com", password=VALID_PASSWORD)
    request = rf.post("/logowanie/")
    request.request_id = "req-2"

    from django.contrib.sessions.middleware import SessionMiddleware

    SessionMiddleware(lambda r: None).process_request(request)

    with pytest.raises(ValidationAppError) as exc_info:
        AuthenticationService.login(request, "login2@example.com", "wrong-password")

    assert exc_info.value.status_code == 401
    assert AuditLog.objects.filter(event=AuditEvent.USER_LOGIN_FAILED).exists()


@pytest.mark.django_db
def test_password_reset_request_is_silent_for_unknown_email():
    PasswordResetService.request_reset("unknown@example.com")

    assert len(mail.outbox) == 0
    assert not AccountToken.objects.exists()


@pytest.mark.django_db
def test_password_reset_full_cycle_invalidates_old_password():
    user = User.objects.create_user(email="reset@example.com", password=VALID_PASSWORD)

    PasswordResetService.request_reset("reset@example.com")
    assert len(mail.outbox) == 1

    token = AccountToken.objects.get(
        user=user, purpose=AccountTokenPurpose.PASSWORD_RESET
    )
    raw_token = generate_public_token()
    token.token_hash = hash_token(raw_token)
    token.save(update_fields=["token_hash"])

    new_password = "Nowy-Bezpieczny-Pass!42"
    PasswordResetService.confirm_reset(raw_token, new_password)

    user.refresh_from_db()
    assert user.check_password(new_password)
    assert not user.check_password(VALID_PASSWORD)
    assert AuditLog.objects.filter(
        actor=user, event=AuditEvent.PASSWORD_CHANGED
    ).exists()


@pytest.mark.django_db
def test_password_reset_invalidates_other_outstanding_tokens():
    user = User.objects.create_user(email="multi@example.com", password=VALID_PASSWORD)

    first_raw = generate_public_token()
    second_raw = generate_public_token()
    AccountToken.objects.create(
        user=user,
        purpose=AccountTokenPurpose.PASSWORD_RESET,
        token_hash=hash_token(first_raw),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    AccountToken.objects.create(
        user=user,
        purpose=AccountTokenPurpose.PASSWORD_RESET,
        token_hash=hash_token(second_raw),
        expires_at=timezone.now() + timedelta(hours=1),
    )

    PasswordResetService.confirm_reset(first_raw, "Another-Strong-Pass!7")

    with pytest.raises(ValidationAppError):
        PasswordResetService.confirm_reset(second_raw, "Yet-Another-Pass!9")
