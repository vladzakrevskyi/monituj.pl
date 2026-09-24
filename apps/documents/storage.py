from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage

from apps.documents import encryption

private_storage = FileSystemStorage(location=str(settings.PRIVATE_STORAGE_ROOT))


def save_document_file(storage_key, content):
    """Writes a document's bytes - encrypted when a master key is set - and
    returns the fields the Document row needs to read them back."""
    if encryption.enabled():
        # The path is authenticated too: the file only opens in its own place.
        blob, wrapped, wrapping_key_id = encryption.encrypt(
            content, storage_key.encode()
        )
    else:
        blob, wrapped, wrapping_key_id = content, "", ""
    saved = private_storage.save(storage_key, ContentFile(blob))
    if saved != storage_key:  # never happens with random names; never guess
        private_storage.delete(saved)
        raise RuntimeError(f"Storage renamed {storage_key!r} to {saved!r}")
    return {"wrapped_key": wrapped, "encryption_key_id": wrapping_key_id}


def read_document_file(document):
    with private_storage.open(document.storage_key, "rb") as handle:
        blob = handle.read()
    if not document.wrapped_key:
        return blob  # stored before encryption was switched on
    return encryption.decrypt(
        blob,
        document.wrapped_key,
        document.encryption_key_id,
        document.storage_key.encode(),
    )
