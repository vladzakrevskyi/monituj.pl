"""Questions to a client - "Co to za przelew 1 250 zł z 12.09?".

The sender asks; the client answers in words (a file if they like), with
no account, from the link in the email; Monituj reminds them until they do.
Next to the question the sender keeps a note of why they asked
(Request.private_note) - for them and their team only, never shown to the
client - so when the answer comes a week later, the question, the reason and
the answer are in one place.

Under the hood a question is a request with one item of the kind QUESTION:
the link, the deadline and the reminders are the ones every request has.
What is said is a conversation (QuestionMessage): the question, the client's
answers, the sender's follow-ups ("Dopytaj") - each kept, in order. The item
keeps the state: waiting for the client (brak / odrzucony after a
follow-up), answered (dostarczony), "Wyjaśnione" (zaakceptowany)."""

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.common.exceptions import ValidationAppError
from apps.notifications.inbox import notify_answered
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService
from apps.requests.models import (
    QuestionMessage,
    QuestionMessageAuthor,
    RequestItemKind,
    RequestItemStatus,
)
from apps.requests.services import CLOSED_MESSAGE, RequestService

MAX_QUESTION = 2000
MAX_NOTE = 2000
MAX_ANSWER = 5000
# The question's first line, shortened, names the request in lists and emails.
TITLE_LENGTH = 90


def title_of(question):
    lines = (question or "").strip().splitlines()
    first_line = " ".join(lines[0].split()) if lines else ""
    if len(first_line) <= TITLE_LENGTH:
        return first_line
    return first_line[: TITLE_LENGTH - 1].rsplit(" ", 1)[0] + "…"


def _clean_text(text, limit):
    lines = [line.rstrip() for line in (text or "").strip().splitlines()]
    return "\n".join(lines)[:limit].strip()


def _writer(django_request):
    user = getattr(django_request, "user", None)
    return user if user is not None and user.is_authenticated else None


def thread(item):
    """The conversation, oldest first."""
    return list(item.messages.all())


def last_exchange(item):
    """-> (what the sender asked last, the client's messages since) - what an
    email about new answers shows."""
    asked, answers = item.description, []
    for message in thread(item):
        if message.from_client:
            answers.append(message.text)
        else:
            asked, answers = message.text, []
    return asked, answers


def _still_open(request_item):
    if request_item.kind != RequestItemKind.QUESTION:
        raise ValidationAppError("To nie jest pytanie.", code="NOT_A_QUESTION")
    if request_item.request.closed_at is not None:
        raise ValidationAppError(CLOSED_MESSAGE, code="REQUEST_CLOSED")
    if request_item.status == RequestItemStatus.ZAAKCEPTOWANY:
        raise ValidationAppError(
            "Sprawa jest już wyjaśniona.", code="ITEM_ALREADY_ACCEPTED"
        )


def ask(
    owner,
    client_id,
    question,
    note="",
    deadline=None,
    reminder_settings=None,
    request=None,
):
    """Sends the question to the client. -> the request."""
    question = _clean_text(question, MAX_QUESTION)
    if len(question) < 5:
        raise ValidationAppError("Napisz pytanie do klienta.", code="QUESTION_EMPTY")
    request_obj = RequestService.create(
        owner=owner,
        client_id=client_id,
        name=title_of(question),
        description="",
        deadline=deadline,
        item_names=[title_of(question)],
        reminder_settings=reminder_settings,
        request=request,
        question=question,
        private_note=_clean_text(note, MAX_NOTE),
    )
    QuestionMessage.objects.create(
        item=request_obj.question_item,
        author=QuestionMessageAuthor.SENDER,
        written_by=_writer(request) or owner,
        text=question,
    )
    return request_obj


@transaction.atomic
def answer(request_item, text, django_request=None):
    """The client's message - an answer, or more to it, until the sender has
    marked the matter "Wyjaśnione". Added to the conversation, never over
    what was said before."""
    _still_open(request_item)
    text = _clean_text(text, MAX_ANSWER)
    if not text:
        raise ValidationAppError("Napisz odpowiedź.", code="ANSWER_EMPTY")
    QuestionMessage.objects.create(
        item=request_item, author=QuestionMessageAuthor.CLIENT, text=text
    )
    # The latest answer, for lists and the morning email.
    request_item.answer = text
    request_item.answered_at = timezone.now()
    request_item.status = RequestItemStatus.DOSTARCZONY
    request_item.save(update_fields=["answer", "answered_at", "status", "updated_at"])
    AuditService.log(
        AuditEvent.QUESTION_ANSWERED,
        target=request_item,
        request=django_request,
        metadata={"answer": text[:500]},
    )
    notify_answered(request_item)
    return request_item


@transaction.atomic
def follow_up(request_item, text, django_request=None):
    """ "Dopytaj": the sender asks more. The client gets an email, the
    reminders start again, and everything said so far stays."""
    _still_open(request_item)
    text = _clean_text(text, MAX_QUESTION)
    if not text:
        raise ValidationAppError("Napisz, o co jeszcze pytasz.", code="REASON_REQUIRED")
    request_obj = request_item.request
    QuestionMessage.objects.create(
        item=request_item,
        author=QuestionMessageAuthor.SENDER,
        written_by=_writer(django_request) or request_obj.created_by,
        text=text,
    )
    request_item.status = RequestItemStatus.ODRZUCONY
    request_item.rejection_reason = text
    request_item.save(update_fields=["status", "rejection_reason", "updated_at"])
    AuditService.log(
        AuditEvent.QUESTION_FOLLOWED_UP,
        actor=_writer(django_request) or request_obj.created_by,
        target=request_item,
        request=django_request,
        metadata={"reason": text[:500]},
    )
    EmailService.send(
        EmailTemplate.REJECTION,
        to_email=request_obj.client.email,
        context={
            "item_name": request_item.name,
            "reason": text,
            "confirm": False,
            "question": request_item.description,
        },
        request=request_obj,
    )
    return request_item


@transaction.atomic
def resolve(request_item, django_request=None):
    """ "Wyjaśnione": the answer is enough - no more reminders."""
    _still_open(request_item)
    if request_item.status != RequestItemStatus.DOSTARCZONY:
        raise ValidationAppError(
            "Poczekaj na odpowiedź klienta.", code="ITEM_NOT_DELIVERED"
        )
    request_obj = request_item.request
    request_item.status = RequestItemStatus.ZAAKCEPTOWANY
    request_item.rejection_reason = ""
    request_item.save(update_fields=["status", "rejection_reason", "updated_at"])
    AuditService.log(
        AuditEvent.QUESTION_RESOLVED,
        actor=_writer(django_request) or request_obj.created_by,
        target=request_item,
        request=django_request,
    )
    return request_item


def save_note(request_obj, note):
    request_obj.private_note = _clean_text(note, MAX_NOTE)
    request_obj.save(update_fields=["private_note", "updated_at"])
    return request_obj


def for_owner(owner):
    """The owner's questions, newest first - with their one item."""
    from apps.requests.models import Request

    return (
        Request.objects.filter(
            created_by=owner,
            items__kind=RequestItemKind.QUESTION,
            awaiting_confirmation=False,
        )
        .select_related("client")
        .prefetch_related("items")
        .distinct()
        .order_by("-created_at")
    )
