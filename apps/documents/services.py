import secrets

from django.core.files.base import ContentFile
from django.db.models import Sum
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.common.exceptions import (
    NotFoundAppError,
    PermissionDeniedAppError,
    ValidationAppError,
)
from apps.documents.models import Document, DocumentStatus
from apps.documents.storage import private_storage
from apps.documents.validation import validate_upload
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

        request_item.status = RequestItemStatus.DOSTARCZONY
        request_item.save(update_fields=["status", "updated_at"])

        AuditService.log(
            AuditEvent.DOCUMENT_UPLOADED, target=document, request=django_request
        )

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
        private_storage.save(storage_key, ContentFile(validated.content))

        safe_original_name = uploaded_file_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1][
            :255
        ]

        return Document.objects.create(
            request_item=request_item,
            storage_key=storage_key,
            original_filename=safe_original_name,
            content_type=validated.mime_type,
            size=validated.size,
            checksum=validated.checksum,
            uploaded_by_session_key=session_key,
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
    def reject(request_item, reason, request=None):
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
            and request_obj.created_by_id == user.id
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
