"""The client's card (/klienci/<id>/): everything about one client in one
place, for when you sit down to their books -

- what is open: questions waiting for an answer (and for how long), answers
  to read, requests still missing documents;
- notes about the client, the team's instead of sticky notes (ClientNote);
- the history: every event about the client, their requests, questions and
  documents, newest first, from the audit log.
"""

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils import timezone

from apps.audit.models import AuditEvent, AuditLog
from apps.audit.services import translate_event
from apps.clients.models import Client
from apps.documents.models import Document
from apps.requests.models import (
    Request,
    RequestItem,
    RequestItemKind,
    RequestItemStatus,
)
from apps.requests.services import in_progress

HISTORY_PAGE = 40
MAX_NOTE = 1000

# Not worth a line in the history: the sender's own downloads.
HIDDEN_EVENTS = {AuditEvent.FILE_DOWNLOAD}
FILTERS = [
    ("wszystko", "Wszystko"),
    ("pytania", "Pytania"),
    ("dokumenty", "Dokumenty"),
    ("przypomnienia", "Prośby i przypomnienia"),
    ("notatki", "Notatki"),
]
DOCUMENT_EVENTS = {
    AuditEvent.DOCUMENT_UPLOADED,
    AuditEvent.DOCUMENT_ACCEPTED,
    AuditEvent.DOCUMENT_REJECTED,
    AuditEvent.FILE_DELETED,
    AuditEvent.DOCUMENTS_ANONYMIZED,
    AuditEvent.ITEM_NOT_APPLICABLE,
    AuditEvent.NOT_APPLICABLE_UNDONE,
    AuditEvent.NOT_APPLICABLE_ACCEPTED,
    AuditEvent.NOT_APPLICABLE_REFUSED,
    AuditEvent.ITEM_CONFIRMED,
    AuditEvent.CONFIRMATION_UNDONE,
}
# Done by the client from their link (no account behind them).
CLIENT_EVENTS = {
    AuditEvent.DOCUMENT_UPLOADED,
    AuditEvent.FILE_DELETED,
    AuditEvent.ITEM_NOT_APPLICABLE,
    AuditEvent.NOT_APPLICABLE_UNDONE,
    AuditEvent.ITEM_CONFIRMED,
    AuditEvent.CONFIRMATION_UNDONE,
    AuditEvent.QUESTION_ANSWERED,
    AuditEvent.PUBLIC_LINK_ACCESSED,
}
REQUEST_EVENTS = {
    AuditEvent.REQUEST_CREATED,
    AuditEvent.REQUEST_UPDATED,
    AuditEvent.REQUEST_CLOSED,
    AuditEvent.REQUEST_REOPENED,
    AuditEvent.INVITATION_SENT,
    AuditEvent.REMINDER_SENT,
    AuditEvent.PUBLIC_LINK_ACCESSED,
}


def open_matters(owner, client):
    """-> {"waiting": [...], "to_review": [...], "missing": [...]}."""
    today = timezone.localdate()
    questions = (
        RequestItem.objects.filter(
            request__client=client,
            request__created_by=owner,
            request__closed_at__isnull=True,
            request__awaiting_confirmation=False,
            kind=RequestItemKind.QUESTION,
        )
        .select_related("request")
        .order_by("request__created_at")
    )
    waiting, to_review = [], []
    for item in questions:
        days = (today - timezone.localtime(item.request.created_at).date()).days
        entry = {"item": item, "request": item.request, "days": days}
        if item.status in (RequestItemStatus.BRAK, RequestItemStatus.ODRZUCONY):
            waiting.append(entry)
        elif item.status == RequestItemStatus.DOSTARCZONY:
            to_review.append(entry)
    missing = []
    now = timezone.now()
    for request_obj in (
        in_progress(owner).filter(client=client).order_by("deadline", "created_at")
    ):
        names = list(
            request_obj.items.filter(
                status__in=[RequestItemStatus.BRAK, RequestItemStatus.ODRZUCONY]
            )
            .order_by("id")
            .values_list("name", flat=True)
        )
        if not names:
            continue
        missing.append(
            {
                "request": request_obj,
                "names": names,
                "overdue": bool(request_obj.deadline and request_obj.deadline < now),
            }
        )
    waiting.sort(key=lambda entry: -entry["days"])
    from apps.agenda.models import PersonalReminder

    reminders = list(
        PersonalReminder.objects.filter(
            account=owner, client=client, done_at__isnull=True
        ).select_related("author")
    )
    return {
        "waiting": waiting,
        "to_review": to_review,
        "missing": missing,
        "reminders": reminders,
    }


def history(client, viewer, kind="wszystko", pages=1):
    """The client's events, newest first: (entries, has_more)."""
    requests = {r.pk: r for r in Request.objects.filter(client=client)}
    items = {i.pk: i for i in RequestItem.objects.filter(request__client=client)}
    documents = {
        d.pk: d
        for d in Document.objects.filter(request_item__request__client=client).only(
            "pk", "request_item_id", "original_filename"
        )
    }
    types = ContentType.objects.get_for_models(Client, Request, RequestItem, Document)
    entries = AuditLog.objects.filter(
        Q(content_type=types[Client], object_id=client.pk)
        | Q(content_type=types[Request], object_id__in=list(requests))
        | Q(content_type=types[RequestItem], object_id__in=list(items))
        | Q(content_type=types[Document], object_id__in=list(documents))
    ).exclude(event__in=HIDDEN_EVENTS)
    if kind == "dokumenty":
        entries = entries.filter(event__in=DOCUMENT_EVENTS)
    elif kind == "przypomnienia":
        entries = entries.filter(event__in=REQUEST_EVENTS)
    elif kind == "notatki":
        entries = entries.filter(event=AuditEvent.CLIENT_NOTE_ADDED)
    entries = entries.select_related("actor", "content_type").order_by(
        "-created_at", "-id"
    )
    questions = {
        i.request_id: i for i in items.values() if i.kind == RequestItemKind.QUESTION
    }
    shown = []
    limit = HISTORY_PAGE * max(pages, 1)
    # A question filter is about what the entry concerns, not its event.
    for entry in entries.iterator():
        line = _describe(entry, types, requests, items, documents, questions, viewer)
        if kind == "pytania" and not line["question"]:
            continue
        shown.append(line)
        if len(shown) > limit:
            break
    return shown[:limit], len(shown) > limit


def _describe(entry, types, requests, items, documents, questions, viewer):
    request_obj = item = document = None
    if entry.content_type_id == types[Request].pk:
        request_obj = requests.get(entry.object_id)
    elif entry.content_type_id == types[RequestItem].pk:
        item = items.get(entry.object_id)
    elif entry.content_type_id == types[Document].pk:
        document = documents.get(entry.object_id)
        item = items.get(document.request_item_id) if document else None
    if item is not None:
        request_obj = requests.get(item.request_id)
    if entry.actor is None:
        who = "klient" if entry.event in CLIENT_EVENTS else "Monituj"
    elif viewer is not None and entry.actor_id == viewer.pk:
        who = "Ty"
    else:
        who = entry.actor.display_name or entry.actor.email
    question = questions.get(request_obj.pk) if request_obj is not None else None
    details = []
    if question is not None:
        details.append(f"Pytanie: {question.description[:140]}")
        if entry.event == AuditEvent.QUESTION_ANSWERED:
            # What was answered then - older entries only know the latest.
            said = (entry.metadata or {}).get("answer") or question.answer
            if said:
                details.append(f"Odpowiedź: {said[:200]}")
    elif item is not None:
        details.append(item.name)
    if document is not None:
        details.append(document.original_filename)
    if request_obj is not None and question is None:
        details.append(f"Prośba: {request_obj.name}")
    reason = (entry.metadata or {}).get("reason")
    if reason:
        details.append(f"„{reason}”")
    return {
        "at": entry.created_at,
        "label": translate_event(entry.event, question=question is not None),
        "who": who,
        "details": details,
        "request": request_obj,
        "question": question is not None,
    }
