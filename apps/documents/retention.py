from datetime import timedelta

from django.db import transaction
from django.db.models import DurationField, ExpressionWrapper, F
from django.utils import timezone

from apps.accounts.services import GUEST_OWNER_EMAIL
from apps.audit.models import AuditEvent
from apps.audit.services import AuditService
from apps.documents.models import Document
from apps.documents.storage import private_storage
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService


def expires_at(document):
    return document.uploaded_at + timedelta(
        days=document.request_item.request.retention_days
    )


class DocumentRetentionService:
    """Deletes uploaded files once their request's retention period has
    passed. The Document row survives as an empty placeholder (no filename,
    no storage key, no checksum) so the request history stays readable, but
    nothing identifying remains in storage or in the database."""

    @staticmethod
    def expired_documents(now=None):
        now = now or timezone.now()
        retention = ExpressionWrapper(
            F("request_item__request__retention_days") * timedelta(days=1),
            output_field=DurationField(),
        )
        return (
            Document.objects.filter(
                anonymized_at__isnull=True, request_item__isnull=False
            )
            .annotate(expires=F("uploaded_at") + retention)
            .filter(expires__lte=now)
            .select_related(
                "request_item__request__client", "request_item__request__created_by"
            )
        )

    @staticmethod
    def anonymize_expired(now=None):
        now = now or timezone.now()
        by_request = {}
        for document in DocumentRetentionService.expired_documents(now):
            by_request.setdefault(document.request_item.request, []).append(document)

        for request_obj, documents in by_request.items():
            DocumentRetentionService._anonymize_for_request(request_obj, documents, now)
        return sum(len(docs) for docs in by_request.values())

    @staticmethod
    def _anonymize_for_request(request_obj, documents, now):
        with transaction.atomic():
            for document in documents:
                private_storage.delete(document.storage_key)
                document.storage_key = f"anonymized/{document.pk}"
                document.original_filename = ""
                document.content_type = ""
                document.size = 0
                document.checksum = ""
                document.uploaded_by_session_key = ""
                document.anonymized_at = now
                document.save()
            AuditService.log(
                AuditEvent.DOCUMENTS_ANONYMIZED,
                target=request_obj,
                metadata={"count": len(documents)},
            )

        context = {
            "request_name": request_obj.name,
            "count": len(documents),
            "retention_days": request_obj.retention_days,
        }
        owner = request_obj.created_by
        if owner.email != GUEST_OWNER_EMAIL:
            EmailService.send(
                EmailTemplate.ANONYMIZED_OWNER,
                to_email=owner.email,
                context=context,
                request=request_obj,
            )
        EmailService.send(
            EmailTemplate.ANONYMIZED_CLIENT,
            to_email=request_obj.client.email,
            context=context,
            request=request_obj,
        )
