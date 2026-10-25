"""Questions to a client - "Co to za przelew 1 250 zł z 12.09?".

The sender asks; the client answers in words (a file if they like), with
no account, from the link in the email; Monituj reminds them until they do.
Next to the question the sender keeps a note of why they asked
(Request.private_note) - for them and their team only, never shown to the
client - so when the answer comes a week later, the question, the reason and
the answer are in one place.

Under the hood a question is a request with one item of the kind QUESTION:
the link, the deadline, the reminders, the notices and "accept" are the
ones every request has. "Wyjaśnione" accepts the answer; "Dopytaj" sends
it back with a follow-up (DocumentReviewService.reject)."""

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.common.exceptions import ValidationAppError
from apps.notifications.inbox import notify_answered
from apps.requests.models import RequestItemKind, RequestItemStatus
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
    return RequestService.create(
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


@transaction.atomic
def answer(request_item, text, django_request=None):
    """The client's answer - again if they want to correct it, until the
    sender has marked it "Wyjaśnione"."""
    if request_item.kind != RequestItemKind.QUESTION:
        raise ValidationAppError("To nie jest pytanie.", code="NOT_A_QUESTION")
    if request_item.request.closed_at is not None:
        raise ValidationAppError(CLOSED_MESSAGE, code="REQUEST_CLOSED")
    if request_item.status == RequestItemStatus.ZAAKCEPTOWANY:
        raise ValidationAppError(
            "Nadawca uznał już tę sprawę za wyjaśnioną.", code="ITEM_ALREADY_ACCEPTED"
        )
    text = _clean_text(text, MAX_ANSWER)
    if not text:
        raise ValidationAppError("Napisz odpowiedź.", code="ANSWER_EMPTY")
    request_item.answer = text
    request_item.answered_at = timezone.now()
    request_item.status = RequestItemStatus.DOSTARCZONY
    request_item.save(update_fields=["answer", "answered_at", "status", "updated_at"])
    AuditService.log(
        AuditEvent.QUESTION_ANSWERED, target=request_item, request=django_request
    )
    notify_answered(request_item)
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
