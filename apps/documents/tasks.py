from celery import shared_task

from apps.documents.retention import DocumentRetentionService


@shared_task
def anonymize_expired_documents():
    return DocumentRetentionService.anonymize_expired()
