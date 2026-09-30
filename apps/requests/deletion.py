"""Deleting a request - or a client with everything ever sent to them.

What the owner deletes is gone for good, the same way as when an account is
deleted (apps/accounts/erasure.py): the request with its items, reminders
and access password, the uploaded files (from the storage too), the email
log and the audit entries about it (they hold the recipient's address and
file names). A client deleted "with history" also leaves their recurring
requests. This is how an owner answers a client's right to erasure
(art. 17 RODO) without deleting the whole account.

What stays is one audit entry that something was deleted - with counts,
never names or addresses."""

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q

from apps.audit.models import AuditEvent, AuditLog
from apps.audit.services import AuditService
from apps.clients.models import Client
from apps.documents.models import Document
from apps.documents.storage import private_storage
from apps.notifications.models import EmailLog
from apps.requests.models import RecipientAccess, Request, RequestItem


def _erase(requests):
    """Deletes these requests and all that hangs on them. -> (requests,
    files) counted."""
    items = RequestItem.objects.filter(request__in=requests)
    documents = Document.objects.filter(request_item__in=items)
    storage_keys = list(documents.values_list("storage_key", flat=True))
    types = {
        model: ContentType.objects.get_for_model(model)
        for model in (Request, RequestItem, Document)
    }
    AuditLog.objects.filter(
        Q(content_type=types[Request], object_id__in=requests.values("pk"))
        | Q(content_type=types[RequestItem], object_id__in=items.values("pk"))
        | Q(content_type=types[Document], object_id__in=documents.values("pk"))
    ).delete()
    EmailLog.objects.filter(request__in=requests).delete()
    count = requests.count()
    requests.delete()
    # Files go last and only once the database changes are certain.
    transaction.on_commit(
        lambda: [private_storage.delete(key) for key in storage_keys if key]
    )
    return count, len(storage_keys)


def _forget_recipient(email):
    """The recipient's "all my requests" link goes with their last request
    from anyone."""
    if not Request.objects.filter(client__email__iexact=email).exists():
        RecipientAccess.objects.filter(email__iexact=email).delete()


def summary(client):
    """What deleting the client with history removes - for the confirmation."""
    requests = Request.objects.filter(client=client)
    return {
        "requests": requests.count(),
        "files": Document.objects.filter(request_item__request__in=requests).count(),
        "recurring": client.recurring_requests.count(),
    }


@transaction.atomic
def delete_requests(owner, request_ids, with_clients=False, django_request=None):
    """The owner's requests with these ids - and with with_clients also the
    clients they went to, each with all of their requests (the unselected
    ones too) and their place in recurring requests. -> {"requests",
    "files", "clients"} removed."""
    requests = Request.objects.filter(created_by=owner, pk__in=request_ids)
    emails = set(requests.values_list("client__email", flat=True))
    client_ids = set(requests.values_list("client_id", flat=True))
    removed = {"requests": 0, "files": 0, "clients": 0}
    if with_clients:
        for client in Client.objects.filter(owner=owner, pk__in=client_ids):
            gone = delete_client_with_history(client, django_request=django_request)
            removed["requests"] += gone["requests"]
            removed["files"] += gone["files"]
            removed["clients"] += 1
    else:
        count, files = _erase(requests)
        removed.update(requests=count, files=files)
        for email in emails:
            _forget_recipient(email)
        AuditService.log(
            AuditEvent.REQUEST_DELETED,
            actor=owner,
            request=django_request,
            metadata={"requests": count, "files": files},
        )
    return removed


def delete_request(request_obj, with_client=False, django_request=None):
    return delete_requests(
        request_obj.created_by,
        [request_obj.pk],
        with_clients=with_client,
        django_request=django_request,
    )


@transaction.atomic
def delete_client_with_history(client, django_request=None):
    """The client, every request sent to them, their files, and their place
    in recurring requests (a recurring request left with nobody goes too).
    -> the summary of what was removed."""
    removed = summary(client)
    owner, email = client.owner, client.email
    _erase(Request.objects.filter(client=client))
    for schedule in client.recurring_requests.all():
        schedule.clients.remove(client)
        if not schedule.clients.exists():
            schedule.delete()
    AuditLog.objects.filter(
        content_type=ContentType.objects.get_for_model(Client), object_id=client.pk
    ).delete()
    client.delete()
    _forget_recipient(email)
    AuditService.log(
        AuditEvent.CLIENT_DELETED,
        actor=owner,
        request=django_request,
        metadata={"with_history": True, **removed},
    )
    return removed
