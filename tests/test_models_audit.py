import pytest
from django.contrib.contenttypes.models import ContentType

from apps.audit.models import AuditEvent, AuditLog


@pytest.mark.django_db
def test_audit_log_links_to_arbitrary_target(client_record, user):
    log = AuditLog.objects.create(
        actor=user,
        event=AuditEvent.CLIENT_CREATED,
        content_type=ContentType.objects.get_for_model(client_record),
        object_id=client_record.pk,
    )

    assert log.target == client_record


@pytest.mark.django_db
def test_audit_log_is_append_only(user):
    log = AuditLog.objects.create(actor=user, event=AuditEvent.USER_LOGIN)

    log.event = AuditEvent.USER_LOGIN_FAILED
    with pytest.raises(ValueError):
        log.save()


@pytest.mark.django_db
def test_audit_log_survives_actor_deletion(user):
    log = AuditLog.objects.create(actor=user, event=AuditEvent.USER_REGISTERED)

    user.delete()
    log.refresh_from_db()

    assert log.actor is None
