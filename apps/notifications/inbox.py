"""Telling a sender that documents arrived - or that the recipient doesn't
have one ("Nie dotyczy"): a notice in the panel at once, and an email a
moment later.

The email waits until the recipient has stopped uploading for a minute, so
ten files sent in a row make one email listing all ten, not ten emails.
Nothing goes out for notices the sender has already seen in the panel, nor
when the "komplet dokumentów" email has told them everything already.
"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.notifications.models import (
    EmailLog,
    EmailTemplate,
    Notification,
    NotificationKind,
)
from apps.notifications.services import EmailService
from apps.requests.models import RequestItemStatus

QUIET_PERIOD = timedelta(minutes=1)
# Someone uploading non-stop still gets their sender an email this often.
MAX_DELAY = timedelta(minutes=10)


def notify_upload(document):
    owner = document.request_item.request.created_by
    # The shared account behind old no-account requests has no one to tell.
    if not owner.is_active:
        return None
    return Notification.objects.create(
        user=owner, kind=NotificationKind.DOCUMENT_UPLOADED, document=document
    )


def notify_not_applicable(request_item):
    """One notice per answer - marking again before the email went out
    doesn't add another (see forget_not_applicable)."""
    owner = request_item.request.created_by
    if not owner.is_active:
        return None
    notice, _ = Notification.objects.get_or_create(
        user=owner,
        kind=NotificationKind.NOT_APPLICABLE,
        request_item=request_item,
        emailed_at__isnull=True,
        read_at__isnull=True,
    )
    return notice


def forget_not_applicable(request_item):
    """The recipient took it back before the sender was told - nothing to
    tell any more."""
    Notification.objects.filter(
        kind=NotificationKind.NOT_APPLICABLE,
        request_item=request_item,
        emailed_at__isnull=True,
    ).delete()


def unread_count(user):
    return Notification.objects.filter(user=user, read_at__isnull=True).count()


def for_user(user):
    return Notification.objects.filter(user=user).select_related(
        "document__request_item__request__client", "request_item__request__client"
    )


def mark_read(user, request_obj=None):
    notices = Notification.objects.filter(user=user, read_at__isnull=True)
    if request_obj is not None:
        notices = notices.filter(
            Q(document__request_item__request=request_obj)
            | Q(request_item__request=request_obj)
        )
    return notices.update(read_at=timezone.now())


def _pending_by_request():
    pending = Notification.objects.filter(emailed_at__isnull=True).select_related(
        "user",
        "document__request_item__request__client",
        "request_item__request__client",
    )
    groups = {}
    for notice in pending.order_by("created_at", "id"):
        request_obj = notice.item.request
        groups.setdefault(request_obj.pk, (request_obj, []))[1].append(notice)
    return groups.values()


def _progress(request_obj):
    delivered = request_obj.items.filter(
        status__in=[
            RequestItemStatus.DOSTARCZONY,
            RequestItemStatus.ZAAKCEPTOWANY,
            RequestItemStatus.NIE_DOTYCZY,
        ]
    ).count()
    return f"{delivered} z {request_obj.items.count()}"


def _entry(notice):
    if notice.document_id:
        return {"item": notice.item.name, "file": notice.document.original_filename}
    return {
        "item": notice.item.name,
        "not_applicable": True,
        "reason": notice.item.not_applicable_reason,
    }


def send_pending_upload_emails(now=None):
    now = now or timezone.now()
    sent = 0
    for request_obj, notices in _pending_by_request():
        first, last = notices[0].created_at, notices[-1].created_at
        if now - last < QUIET_PERIOD and now - first < MAX_DELAY:
            continue  # still uploading
        # Claim them first, so a second worker can't send the same email.
        claimed = Notification.objects.filter(
            pk__in=[n.pk for n in notices], emailed_at__isnull=True
        ).update(emailed_at=now)
        if not claimed:
            continue
        owner = notices[0].user
        unseen = [n for n in notices if n.read_at is None]
        complete_told = EmailLog.objects.filter(
            request=request_obj,
            template=EmailTemplate.COMPLETE_OWNER,
            created_at__gte=first,
        ).exists()
        if not unseen or complete_told or not owner.is_active:
            continue
        EmailService.send(
            EmailTemplate.UPLOAD_OWNER,
            to_email=owner.email,
            context={
                "client_name": request_obj.client.name,
                "uploads": [_entry(n) for n in unseen],
                "upload_count": len(unseen),
                # Only "Nie dotyczy" - the email says so instead of "Dotarł".
                "only_not_applicable": all(not n.document_id for n in unseen),
                "progress": _progress(request_obj),
            },
            request=request_obj,
        )
        sent += 1
    return sent
