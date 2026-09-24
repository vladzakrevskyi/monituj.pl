import pytest

from apps.notifications.models import EmailLog, EmailStatus, EmailTemplate


@pytest.mark.django_db
def test_email_log_records_delivery(request_record):
    log = EmailLog.objects.create(
        recipient_email="klient@example.com",
        template=EmailTemplate.INVITATION,
        request=request_record,
        status=EmailStatus.SENT,
    )

    assert str(log) == "zaproszenie to klient@example.com"


@pytest.mark.django_db
def test_email_log_survives_request_deletion(request_record):
    log = EmailLog.objects.create(
        recipient_email="klient@example.com",
        template=EmailTemplate.REMINDER,
        request=request_record,
        status=EmailStatus.SENT,
    )

    request_record.delete()
    log.refresh_from_db()

    assert log.request is None
