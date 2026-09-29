from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditEvent, AuditLog
from apps.audit.services import AuditService
from apps.audit.tasks import delete_orphaned_entries
from apps.requests.models import Request


def _aged(entry, days):
    AuditLog.objects.filter(pk=entry.pk).update(
        created_at=timezone.now() - timedelta(days=days)
    )


@pytest.mark.django_db
def test_entries_without_an_account_go_after_a_year(user, client_record):
    kept_request = Request.objects.create(
        client=client_record, created_by=user, name="Zostaje"
    )
    gone_request = Request.objects.create(
        client=client_record, created_by=user, name="Usunięta"
    )
    unknown_login = AuditService.log(
        AuditEvent.USER_LOGIN_FAILED, metadata={"email": "nikt@example.com"}
    )
    recent_login = AuditService.log(
        AuditEvent.USER_LOGIN_FAILED, metadata={"email": "ktos@example.com"}
    )
    link_of_existing = AuditService.log(
        AuditEvent.PUBLIC_LINK_ACCESSED, target=kept_request
    )
    link_of_deleted = AuditService.log(
        AuditEvent.PUBLIC_LINK_ACCESSED, target=gone_request
    )
    owner_action = AuditService.log(
        AuditEvent.REQUEST_CREATED, actor=user, target=kept_request
    )
    for entry in (unknown_login, link_of_existing, link_of_deleted, owner_action):
        _aged(entry, 400)
    gone_request.delete()

    assert delete_orphaned_entries() == 2
    assert set(AuditLog.objects.values_list("pk", flat=True)) == {
        recent_login.pk,
        link_of_existing.pk,
        owner_action.pk,
    }
