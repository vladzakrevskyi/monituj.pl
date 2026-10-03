import secrets

from django.db.models import Sum
from django.utils import timezone

from apps.accounts import team
from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.common.exceptions import (
    NotFoundAppError,
    PermissionDeniedAppError,
    ValidationAppError,
)
from apps.documents.models import Document, DocumentStatus
from apps.documents.storage import private_storage, save_document_file
from apps.documents.validation import validate_upload
from apps.notifications.inbox import (
    forget_not_applicable,
    notify_not_applicable,
    notify_upload,
)
from apps.notifications.models import EmailStatus, EmailTemplate
from apps.notifications.services import EmailService
from apps.requests.models import RequestItemStatus
from apps.requests.received import is_verified_recipient
from apps.requests.services import CLOSED_MESSAGE, PublicAccessService, with_stats

# Generous for real documents, but a leaked link can't fill the disk.
MAX_FILES_PER_ITEM = 20
MAX_BYTES_PER_REQUEST = 500 * 1024 * 1024
UPLOADS_PER_IP_HOUR = 120


def _generate_storage_key(extension: str) -> str:
    date_prefix = timezone.now().strftime("%Y/%m/%d")
    return f"{date_prefix}/{secrets.token_hex(16)}.{extension}"


class UploadDocumentService:
    @staticmethod
    def upload_for_item(request_item, uploaded_file, django_request=None):
        if request_item.request.closed_at is not None:
            raise ValidationAppError(CLOSED_MESSAGE, code="REQUEST_CLOSED")
        if request_item.status == RequestItemStatus.ZAAKCEPTOWANY:
            raise ValidationAppError(
                "Ten dokument został już zaakceptowany.", code="ITEM_ALREADY_ACCEPTED"
            )

        stored = Document.objects.filter(
            request_item__request=request_item.request, anonymized_at__isnull=True
        )
        if stored.filter(request_item=request_item).count() >= MAX_FILES_PER_ITEM:
            raise ValidationAppError(
                f"Do jednego dokumentu można dodać najwyżej {MAX_FILES_PER_ITEM} "
                "plików. Usuń zbędne albo połącz je w jeden plik.",
                code="TOO_MANY_FILES",
            )
        used = stored.aggregate(total=Sum("size"))["total"] or 0
        if used + (uploaded_file.size or 0) > MAX_BYTES_PER_REQUEST:
            raise ValidationAppError(
                "W tej prośbie zabrakło miejsca na kolejne pliki. Skontaktuj się "
                "z nadawcą.",
                code="REQUEST_STORAGE_FULL",
            )

        validated = validate_upload(uploaded_file)

        if Document.objects.filter(
            request_item=request_item, checksum=validated.checksum
        ).exists():
            raise ValidationAppError(
                "Ten plik został już przesłany.", code="DUPLICATE_FILE"
            )

        session_key = ""
        if django_request is not None:
            if not django_request.session.session_key:
                django_request.session.save()
            session_key = django_request.session.session_key or ""

        document = UploadDocumentService._store(
            uploaded_file_name=uploaded_file.name,
            validated=validated,
            request_item=request_item,
            session_key=session_key,
        )

        # A file for an item marked "Nie dotyczy" means it applies after all.
        request_item.status = RequestItemStatus.DOSTARCZONY
        request_item.not_applicable_reason = ""
        request_item.not_applicable_accepted = False
        request_item.save(
            update_fields=[
                "status",
                "not_applicable_reason",
                "not_applicable_accepted",
                "updated_at",
            ]
        )

        AuditService.log(
            AuditEvent.DOCUMENT_UPLOADED, target=document, request=django_request
        )
        notify_upload(document)

        recipient = request_item.request.client.email
        EmailService.send(
            EmailTemplate.UPLOAD_CONFIRMATION,
            to_email=recipient,
            context={"document_name": document.original_filename},
            request=request_item.request,
        )
        UploadDocumentService._maybe_send_complete_email(request_item.request)

        return document

    @staticmethod
    def _store(
        uploaded_file_name,
        validated,
        request_item,
        session_key,
    ):
        storage_key = _generate_storage_key(validated.extension)
        encryption_fields = save_document_file(storage_key, validated.content)

        safe_original_name = uploaded_file_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if validated.converted:
            # IMG_1234.HEIC was stored as a JPG.
            safe_original_name = safe_original_name.rsplit(".", 1)[0] + ".jpg"
        safe_original_name = safe_original_name[:255]

        return Document.objects.create(
            request_item=request_item,
            storage_key=storage_key,
            original_filename=safe_original_name,
            content_type=validated.mime_type,
            size=validated.size,
            checksum=validated.checksum,
            uploaded_by_session_key=session_key,
            **encryption_fields,
        )

    @staticmethod
    def _maybe_send_complete_email(request_obj):
        annotated = with_stats(
            type(request_obj).objects.filter(pk=request_obj.pk)
        ).first()
        if annotated is None or annotated.total_items == 0:
            return
        if annotated.delivered_items != annotated.total_items:
            return

        already_sent = annotated.email_logs.filter(
            template=EmailTemplate.COMPLETE, status=EmailStatus.SENT
        ).exists()
        if already_sent:
            return

        EmailService.send(
            EmailTemplate.COMPLETE,
            to_email=annotated.client.email,
            context={"request_name": annotated.name},
            request=annotated,
        )
        # The sender hears about it too - the shared account behind old
        # no-account requests is inactive and has no real mailbox.
        owner = annotated.created_by
        if owner.is_active:
            EmailService.send(
                EmailTemplate.COMPLETE_OWNER,
                to_email=owner.email,
                context={"request_name": annotated.name},
                request=annotated,
            )


class DocumentReviewService:
    @staticmethod
    def accept(request_item, request=None):
        if request_item.status == RequestItemStatus.NIE_DOTYCZY:
            return NotApplicableService.accept(request_item, request=request)
        if request_item.status != RequestItemStatus.DOSTARCZONY:
            raise ValidationAppError(
                "Można zaakceptować tylko dostarczony dokument.",
                code="ITEM_NOT_DELIVERED",
            )

        request_item.status = RequestItemStatus.ZAAKCEPTOWANY
        request_item.rejection_reason = ""
        request_item.save(update_fields=["status", "rejection_reason", "updated_at"])
        request_item.documents.filter(status=DocumentStatus.UPLOADED).update(
            status=DocumentStatus.ACCEPTED
        )
        AuditService.log(
            AuditEvent.DOCUMENT_ACCEPTED,
            actor=request_item.request.created_by,
            target=request_item,
            request=request,
        )
        return request_item

    @staticmethod
    def to_review(request_obj):
        """Waiting for the sender's decision: files sent, or "Nie dotyczy"
        not accepted yet."""
        from django.db.models import Q

        return request_obj.items.filter(
            Q(status=RequestItemStatus.DOSTARCZONY)
            | Q(
                status=RequestItemStatus.NIE_DOTYCZY,
                not_applicable_accepted=False,
            )
        )

    @staticmethod
    def accept_all(request_obj, request=None):
        """ "Zaakceptuj wszystkie": every item waiting for a decision. -> how
        many."""
        items = list(DocumentReviewService.to_review(request_obj).order_by("id"))
        for item in items:
            DocumentReviewService.accept(item, request=request)
        return len(items)

    @staticmethod
    def reject(request_item, reason, request=None):
        if request_item.status == RequestItemStatus.NIE_DOTYCZY:
            return NotApplicableService.refuse(request_item, reason, request=request)
        if request_item.status != RequestItemStatus.DOSTARCZONY:
            raise ValidationAppError(
                "Można odrzucić tylko dostarczony dokument.", code="ITEM_NOT_DELIVERED"
            )
        if not reason.strip():
            raise ValidationAppError("Podaj powód odrzucenia.", code="REASON_REQUIRED")

        request_item.status = RequestItemStatus.ODRZUCONY
        request_item.rejection_reason = reason
        request_item.save(update_fields=["status", "rejection_reason", "updated_at"])
        request_item.documents.filter(status=DocumentStatus.UPLOADED).update(
            status=DocumentStatus.REJECTED
        )
        AuditService.log(
            AuditEvent.DOCUMENT_REJECTED,
            actor=request_item.request.created_by,
            target=request_item,
            request=request,
            metadata={"reason": reason},
        )
        EmailService.send(
            EmailTemplate.REJECTION,
            to_email=request_item.request.client.email,
            context={"item_name": request_item.name, "reason": reason},
            request=request_item.request,
        )
        return request_item


NOT_APPLICABLE_FIELDS = [
    "status",
    "rejection_reason",
    "not_applicable_reason",
    "not_applicable_accepted",
    "updated_at",
]
MAX_REASON = 500


class NotApplicableService:
    """ "Nie mam tego dokumentu": none this month, or it isn't the recipient's
    to give. Reminders about it stop at once and a request with nothing else
    missing is complete; the sender sees why and may accept it or ask for
    the document after all (back to "Odrzucony", with their reason)."""

    @staticmethod
    def _check_open(request_item):
        if request_item.request.closed_at is not None:
            raise ValidationAppError(CLOSED_MESSAGE, code="REQUEST_CLOSED")

    @staticmethod
    def mark_by_recipient(request_item, reason, django_request=None):
        NotApplicableService._check_open(request_item)
        reason = " ".join((reason or "").split())[:MAX_REASON]
        if not reason:
            raise ValidationAppError(
                "Napisz krótko, dlaczego nie masz tego dokumentu.",
                code="REASON_REQUIRED",
            )
        if request_item.status not in (
            RequestItemStatus.BRAK,
            RequestItemStatus.ODRZUCONY,
        ):
            raise ValidationAppError(
                "Ten dokument jest już przesłany - usuń najpierw plik.",
                code="ITEM_NOT_MISSING",
            )
        request_item.status = RequestItemStatus.NIE_DOTYCZY
        request_item.rejection_reason = ""
        request_item.not_applicable_reason = reason
        request_item.not_applicable_accepted = False
        request_item.save(update_fields=NOT_APPLICABLE_FIELDS)
        AuditService.log(
            AuditEvent.ITEM_NOT_APPLICABLE,
            target=request_item,
            request=django_request,
            metadata={"by": "recipient", "reason": reason},
        )
        notify_not_applicable(request_item)
        UploadDocumentService._maybe_send_complete_email(request_item.request)
        return request_item

    @staticmethod
    def undo_by_recipient(request_item, django_request=None):
        """A click by mistake - while the sender hasn't accepted it yet."""
        NotApplicableService._check_open(request_item)
        if (
            request_item.status != RequestItemStatus.NIE_DOTYCZY
            or request_item.not_applicable_accepted
        ):
            raise ValidationAppError("Tego nie można już cofnąć.", code="CANNOT_UNDO")
        request_item.status = RequestItemStatus.BRAK
        request_item.not_applicable_reason = ""
        request_item.save(update_fields=NOT_APPLICABLE_FIELDS)
        forget_not_applicable(request_item)
        AuditService.log(
            AuditEvent.NOT_APPLICABLE_UNDONE,
            target=request_item,
            request=django_request,
        )
        return request_item

    @staticmethod
    def mark_by_owner(request_item, reason="", request=None):
        """The sender knows it already - e.g. the client said so on the phone."""
        NotApplicableService._check_open(request_item)
        if request_item.status not in (
            RequestItemStatus.BRAK,
            RequestItemStatus.ODRZUCONY,
        ):
            raise ValidationAppError(
                "Można tak oznaczyć tylko brakujący dokument.",
                code="ITEM_NOT_MISSING",
            )
        reason = " ".join((reason or "").split())[:MAX_REASON]
        request_item.status = RequestItemStatus.NIE_DOTYCZY
        request_item.rejection_reason = ""
        request_item.not_applicable_reason = reason
        request_item.not_applicable_accepted = True
        request_item.save(update_fields=NOT_APPLICABLE_FIELDS)
        AuditService.log(
            AuditEvent.ITEM_NOT_APPLICABLE,
            actor=request_item.request.created_by,
            target=request_item,
            request=request,
            metadata={"by": "owner", "reason": reason},
        )
        return request_item

    @staticmethod
    def accept(request_item, request=None):
        request_item.not_applicable_accepted = True
        request_item.save(update_fields=["not_applicable_accepted", "updated_at"])
        AuditService.log(
            AuditEvent.NOT_APPLICABLE_ACCEPTED,
            actor=request_item.request.created_by,
            target=request_item,
            request=request,
        )
        return request_item

    @staticmethod
    def refuse(request_item, reason, request=None):
        """ "Jednak potrzebuję": reminders about it start again."""
        NotApplicableService._check_open(request_item)
        if not reason.strip():
            raise ValidationAppError(
                "Napisz klientowi, dlaczego jednak potrzebujesz tego dokumentu.",
                code="REASON_REQUIRED",
            )
        request_item.status = RequestItemStatus.ODRZUCONY
        request_item.rejection_reason = reason
        request_item.not_applicable_reason = ""
        request_item.not_applicable_accepted = False
        request_item.save(update_fields=NOT_APPLICABLE_FIELDS)
        AuditService.log(
            AuditEvent.NOT_APPLICABLE_REFUSED,
            actor=request_item.request.created_by,
            target=request_item,
            request=request,
            metadata={"reason": reason},
        )
        EmailService.send(
            EmailTemplate.REJECTION,
            to_email=request_item.request.client.email,
            context={"item_name": request_item.name, "reason": reason, "needed": True},
            request=request_item.request,
        )
        return request_item


class DocumentAccessService:
    @staticmethod
    def get_for_download(document_id, django_request):
        document = (
            Document.objects.select_related(
                "request_item__request__client", "request_item__request__created_by"
            )
            .filter(pk=document_id)
            .first()
        )
        if document is None or document.request_item is None or document.is_anonymized:
            raise NotFoundAppError("Nie znaleziono dokumentu.")

        request_obj = document.request_item.request
        user = getattr(django_request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and team.can_work_in(user, request_obj.created_by_id)
        ):
            return document

        # The recipient who proved their address may fetch anything they sent.
        # Someone who only has the link gets just the files sent from their
        # own browser - the link may have been forwarded, and document ids are
        # easy to guess.
        if is_verified_recipient(django_request, request_obj.client.email):
            return document
        session_key = django_request.session.session_key
        if (
            PublicAccessService.has_access(request_obj, django_request)
            and session_key
            and document.uploaded_by_session_key == session_key
        ):
            return document

        raise PermissionDeniedAppError("Brak dostępu do tego zasobu.")


class GuestDeleteService:
    @staticmethod
    def delete_own_upload(document_id, django_request):
        document = (
            Document.objects.select_related("request_item")
            .filter(pk=document_id)
            .first()
        )
        if document is None or document.request_item is None or document.is_anonymized:
            raise NotFoundAppError("Nie znaleziono dokumentu.")

        session_key = django_request.session.session_key
        if not session_key or document.uploaded_by_session_key != session_key:
            raise PermissionDeniedAppError("Brak dostępu do tego zasobu.")

        request_item = document.request_item
        if request_item.request.closed_at is not None:
            raise ValidationAppError(CLOSED_MESSAGE, code="REQUEST_CLOSED")
        if request_item.status == RequestItemStatus.ZAAKCEPTOWANY:
            raise ValidationAppError(
                "Nie można usunąć zaakceptowanego dokumentu.",
                code="ITEM_ALREADY_ACCEPTED",
            )

        private_storage.delete(document.storage_key)
        AuditService.log(
            AuditEvent.FILE_DELETED, target=request_item, request=django_request
        )
        document.delete()

        if not request_item.documents.exists():
            request_item.status = RequestItemStatus.BRAK
            request_item.rejection_reason = ""
            request_item.save(
                update_fields=["status", "rejection_reason", "updated_at"]
            )

        return request_item


class GuestUploadContext:
    @staticmethod
    def all_documents_by_item(request_obj):
        docs = Document.objects.filter(request_item__request=request_obj).order_by(
            "-uploaded_at"
        )
        result: dict[int, list[Document]] = {}
        for doc in docs:
            result.setdefault(doc.request_item_id, []).append(doc)
        return result

    @staticmethod
    def own_documents_by_item(request_obj, session_key):
        if not session_key:
            return {}
        docs = Document.objects.filter(
            request_item__request=request_obj, uploaded_by_session_key=session_key
        ).order_by("-uploaded_at")
        result: dict[int, list[Document]] = {}
        for doc in docs:
            result.setdefault(doc.request_item_id, []).append(doc)
        return result
