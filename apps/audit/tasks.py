from datetime import timedelta

from celery import shared_task
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.audit.models import AuditLog

# Entries that belong to no account - failed logins to unknown addresses, a
# public link of a request that no longer exists (an unconfirmed one, say) -
# are kept a year: long enough to look into an incident, not longer
# (Polityka prywatności). Entries of an account stay while it exists and go
# with it (accounts/erasure.py).
ORPHAN_RETENTION = timedelta(days=365)


def delete_orphaned_entries(now=None):
    """Deletes old entries with no account behind them. Returns how many."""
    cutoff = (now or timezone.now()) - ORPHAN_RETENTION
    old = AuditLog.objects.filter(actor__isnull=True, created_at__lt=cutoff)
    deleted = old.filter(content_type__isnull=True).delete()[0]
    for content_type_id in (
        old.filter(content_type__isnull=False)
        .values_list("content_type", flat=True)
        .distinct()
    ):
        model = ContentType.objects.get_for_id(content_type_id).model_class()
        about = old.filter(content_type_id=content_type_id)
        if model is not None:
            # Only entries whose object is gone - a request that still
            # exists keeps its history for its owner.
            about = about.exclude(object_id__in=model.objects.values("pk"))
        deleted += about.delete()[0]
    return deleted


@shared_task
def delete_old_audit_entries():
    return delete_orphaned_entries()
