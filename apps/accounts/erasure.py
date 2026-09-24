from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.clients.models import Client
from apps.documents.models import Document
from apps.documents.storage import private_storage
from apps.notifications.models import EmailLog
from apps.requests.models import RecipientAccess, Request, RequestItem


@transaction.atomic
def erase_account(user):
    """Removes an account and everything it owns: stored files, documents,
    requests with their items and reminders, clients, email and audit logs,
    tokens and finally the user row. Nothing about the account survives -
    automatic reminders stop by themselves, since the hourly task only looks
    at requests that still exist."""
    requests = Request.objects.filter(created_by=user)
    recipient_emails = set(
        Client.objects.filter(owner=user).values_list("email", flat=True)
    )
    items = RequestItem.objects.filter(request__in=requests)
    documents = Document.objects.filter(request_item__in=items)
    storage_keys = list(documents.values_list("storage_key", flat=True))

    types = {
        model: ContentType.objects.get_for_model(model)
        for model in (Request, RequestItem, Document, Client, User)
    }
    AuditLog.objects.filter(
        Q(actor=user)
        | Q(content_type=types[User], object_id=user.pk)
        | Q(content_type=types[Request], object_id__in=requests.values("pk"))
        | Q(content_type=types[RequestItem], object_id__in=items.values("pk"))
        | Q(content_type=types[Document], object_id__in=documents.values("pk"))
        | Q(
            content_type=types[Client],
            object_id__in=Client.objects.filter(owner=user).values("pk"),
        )
        # Failed logins have no actor, only the typed address.
        | Q(metadata__email__iexact=user.email)
    ).delete()
    EmailLog.objects.filter(
        Q(request__in=requests) | Q(recipient_email__iexact=user.email)
    ).delete()

    requests.delete()
    Client.objects.filter(owner=user).delete()
    user.delete()

    # A recipient's "all my requests" link goes too, unless other senders
    # still have requests for them.
    for email in recipient_emails:
        if not Request.objects.filter(client__email__iexact=email).exists():
            RecipientAccess.objects.filter(email__iexact=email).delete()

    # Files go last and only once the database changes are certain.
    transaction.on_commit(lambda: [private_storage.delete(key) for key in storage_keys])
