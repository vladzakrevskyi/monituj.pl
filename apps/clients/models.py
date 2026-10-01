import uuid

from django.db import models

from apps.accounts.models import User
from apps.common.models import TimeStampedModel


class Client(TimeStampedModel):
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="clients")
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=32, blank=True)
    # 10 digits, checked (apps/common/nip.py); empty when not given.
    nip = models.CharField("NIP", max_length=10, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["owner", "name"])]

    def __str__(self):
        return self.name


class ClientImport(models.Model):
    """A file read for importing, between the upload and the "Importuj"
    click: the table as read, nothing saved as clients yet. One per owner
    (a new upload replaces it), gone after the import or within a day."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="client_imports"
    )
    file_name = models.CharField(max_length=255)
    # Every row of the file as text cells, the first one possibly headers.
    table = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
