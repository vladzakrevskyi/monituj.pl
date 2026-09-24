import pytest

from apps.audit.models import AuditEvent, AuditLog
from apps.audit.services import EVENT_LABELS_PL, AuditService, translate_event
from apps.documents.services import UploadDocumentService
from tests.conftest import make_pdf_upload


def test_every_audit_event_has_a_polish_translation():
    for event in AuditEvent.values:
        label = translate_event(event)
        assert label == EVENT_LABELS_PL[event]
        assert label != event


def test_translate_event_falls_back_to_code_for_unknown_event():
    assert translate_event("SOME_UNMAPPED_EVENT") == "SOME_UNMAPPED_EVENT"


@pytest.mark.django_db
def test_history_for_request_aggregates_across_related_entities(request_item):
    UploadDocumentService.upload_for_item(request_item, make_pdf_upload())

    history = AuditService.history_for_request(request_item.request)

    events = set(history.values_list("event", flat=True))
    assert AuditEvent.DOCUMENT_UPLOADED in events


@pytest.mark.django_db
def test_history_for_request_excludes_unrelated_requests(user, client_record):
    from apps.requests.services import RequestService

    other = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Inne zadanie",
        description="",
        deadline=None,
        item_names=["A"],
    )
    mine = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Moje zadanie",
        description="",
        deadline=None,
        item_names=["B"],
    )

    history = AuditService.history_for_request(mine)

    assert not AuditLog.objects.filter(
        pk__in=history.values_list("pk", flat=True), object_id=other.pk
    ).exists()
