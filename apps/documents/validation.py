import hashlib
import os

import magic

from apps.common.exceptions import ValidationAppError

MAX_UPLOAD_SIZE = 20 * 1024 * 1024

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# What the file's content may be for each extension. Office files are zip
# archives inside, which older libmagic versions report as plain zip.
ALLOWED_TYPES = {
    "pdf": {"application/pdf"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
    "png": {"image/png"},
    "doc": {"application/msword"},
    "xls": {"application/vnd.ms-excel"},
    "docx": {_DOCX, "application/zip"},
    "xlsx": {_XLSX, "application/zip"},
    "csv": {"text/csv", "text/plain"},
}
ALLOWED_EXTENSIONS = set(ALLOWED_TYPES)


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
    if mime_type not in ALLOWED_TYPES[extension]:
        raise ValidationAppError(
            "Ten format pliku nie jest dozwolony.", code="MIME_NOT_ALLOWED"
        )

    checksum = hashlib.sha256(content).hexdigest()
    return ValidatedUpload(
        content=content, extension=extension, mime_type=mime_type, checksum=checksum
    )
