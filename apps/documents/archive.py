"""Every file of a request in one ZIP - what the sender downloads instead of
clicking each file. Folders follow the document list ("01 Faktury
sprzedaży/"), so the archive reads like the request. Files are decrypted
one at a time into a temporary file on disk, never all in memory."""

import logging
import re
import tempfile
import zipfile

from django.core.exceptions import ImproperlyConfigured

from apps.documents.encryption import DecryptionError
from apps.documents.models import Document
from apps.documents.storage import read_document_file

logger = logging.getLogger("monituj")

# Kept in memory up to this size, then spilled to disk.
IN_MEMORY = 20 * 1024 * 1024
UNREADABLE_NOTE = "NIE_UDALO_SIE_OTWORZYC.txt"


def safe_name(value, fallback="plik"):
    """A file or folder name that works on Windows, macOS and Linux."""
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", value or "")
    value = " ".join(value.split()).strip(" .")
    return value[:120] or fallback


def documents_of(request_obj):
    return (
        Document.objects.filter(
            request_item__request=request_obj, anonymized_at__isnull=True
        )
        .select_related("request_item")
        .order_by("request_item_id", "uploaded_at", "id")
    )


def archive_name(request_obj):
    return f"{safe_name(request_obj.client.name)} - {safe_name(request_obj.name)}.zip"


def build(request_obj):
    """Returns (file object at position 0, the documents put in). A file that
    can't be opened is left out and listed in a note inside the archive."""
    items = list(request_obj.items.order_by("id"))
    folder = {
        item.pk: f"{number:02d} {safe_name(item.name, 'dokument')}"
        for number, item in enumerate(items, start=1)
    }
    used = set()
    included, unreadable = [], []
    spool = tempfile.SpooledTemporaryFile(max_size=IN_MEMORY)
    with zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED) as archive:
        for document in documents_of(request_obj):
            try:
                content = read_document_file(document)
            except DecryptionError, ImproperlyConfigured, OSError, ValueError:
                logger.exception("Document %s could not be read", document.pk)
                unreadable.append(document)
                continue
            path = _unique(
                f"{folder[document.request_item_id]}/"
                f"{safe_name(document.original_filename)}",
                used,
            )
            archive.writestr(path, content)
            included.append(document)
        if unreadable:
            archive.writestr(
                UNREADABLE_NOTE,
                "Tych plików nie udało się otworzyć - pobierz je pojedynczo "
                "albo napisz do nas:\n"
                + "\n".join(
                    f"- {folder[d.request_item_id]}: {d.original_filename}"
                    for d in unreadable
                ),
            )
    spool.seek(0)
    return spool, included


def _unique(path, used):
    """faktura.pdf, faktura (2).pdf, ... - two uploads may share a name."""
    candidate, number = path, 2
    stem, dot, extension = path.rpartition(".")
    if not dot or "/" in extension:
        stem, extension = path, ""
    while candidate.lower() in used:
        candidate = f"{stem} ({number}){'.' + extension if extension else ''}"
        number += 1
    used.add(candidate.lower())
    return candidate
