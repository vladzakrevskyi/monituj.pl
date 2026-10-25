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


class ClientNote(models.Model):
    """A dated note about a client - "dzwoniła w sprawie leasingu", "faktury
    za paliwo przynosi papierowo" - instead of sticky notes. Seen by the
    account's whole team on the client's card, never by the client.
    (Client.note is the one standing note from the client's form.)"""

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["client", "created_at"])]

    def __str__(self):
        return self.text[:40]


class ClientImport(models.Model):
    """A file read for importing, between the upload and the "Importuj"
    click: the table as read, nothing saved as clients yet. One per owner
    (a new upload replaces it), gone after the import or within a day."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="client_imports"
    )
    # The workspace the file was uploaded in - the clients go there, even if
    # the person switched to another one before clicking "Importuj".
    account = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
    )
    file_name = models.CharField(max_length=255)
    # Every row of the file as text cells, the first one possibly headers.
    table = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
