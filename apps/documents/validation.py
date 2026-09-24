import hashlib
import os

import magic

from apps.common.exceptions import ValidationAppError

MAX_UPLOAD_SIZE = 20 * 1024 * 1024

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "doc", "docx", "xls", "xlsx", "csv"}

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "text/plain",
    "application/zip",
}


class ValidatedUpload:
    def __init__(self, content: bytes, extension: str, mime_type: str, checksum: str):
        self.content = content
        self.extension = extension
        self.mime_type = mime_type
        self.checksum = checksum
        self.size = len(content)


def validate_upload(uploaded_file) -> ValidatedUpload:
    if uploaded_file.size > MAX_UPLOAD_SIZE:
        raise ValidationAppError("Plik jest za duży.", code="FILE_TOO_LARGE")
    if uploaded_file.size == 0:
        raise ValidationAppError("Plik jest pusty.", code="EMPTY_FILE")

    safe_name = os.path.basename(uploaded_file.name or "")
    extension = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationAppError(
            "Ten format pliku nie jest dozwolony.", code="EXTENSION_NOT_ALLOWED"
        )

    content = uploaded_file.read()
    mime_type = magic.from_buffer(content, mime=True)
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValidationAppError(
            "Ten format pliku nie jest dozwolony.", code="MIME_NOT_ALLOWED"
        )

    checksum = hashlib.sha256(content).hexdigest()
    return ValidatedUpload(
        content=content, extension=extension, mime_type=mime_type, checksum=checksum
    )
