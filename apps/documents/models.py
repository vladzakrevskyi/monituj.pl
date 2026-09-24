from django.db import models

from apps.common.models import TimeStampedModel
from apps.requests.models import RequestItem


class DocumentStatus(models.TextChoices):
    UPLOADED = "uploaded", "Przesłany"
    ACCEPTED = "accepted", "Zaakceptowany"
    REJECTED = "rejected", "Odrzucony"


class Document(TimeStampedModel):
    request_item = models.ForeignKey(
        RequestItem,
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True,
    )
    storage_key = models.CharField(max_length=255, unique=True)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=127)
    size = models.PositiveBigIntegerField()
    checksum = models.CharField(max_length=64)
    status = models.CharField(
        max_length=32, choices=DocumentStatus.choices, default=DocumentStatus.UPLOADED
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by_session_key = models.CharField(max_length=64, blank=True)
    anonymized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["request_item", "status"])]

    def __str__(self):
        return self.original_filename or f"Document {self.pk} (anonymized)"

    @property
    def is_anonymized(self) -> bool:
        return self.anonymized_at is not None
