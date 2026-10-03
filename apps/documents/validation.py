import hashlib
import io
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
    # iPhone photos - stored as JPG (see _heic_to_jpeg).
    "heic": {"image/heic", "image/heif"},
    "heif": {"image/heic", "image/heif"},
}
ALLOWED_EXTENSIONS = set(ALLOWED_TYPES)
CONVERTED_TO_JPEG = {"heic", "heif"}
# A photo, not a decompression bomb: ~50 megapixels is far above any phone.
MAX_IMAGE_PIXELS = 50_000_000


class ValidatedUpload:
    def __init__(
        self,
        content: bytes,
        extension: str,
        mime_type: str,
        checksum: str,
        converted: bool = False,
    ):
        self.content = content
        self.extension = extension
        self.mime_type = mime_type
        self.checksum = checksum
        self.size = len(content)
        # A HEIC photo turned into a JPG - the file name says .jpg too.
        self.converted = converted


def _heic_to_jpeg(content: bytes) -> bytes:
    """iPhone photos (HEIC) as JPG - something every computer opens. The
    photo is turned the way it was taken, and its metadata (place, device)
    is left out."""
    import pillow_heif
    from PIL import Image, ImageOps

    pillow_heif.register_heif_opener()
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValidationAppError(
                    "Zdjęcie ma zbyt dużą rozdzielczość.", code="IMAGE_TOO_LARGE"
                )
            photo = ImageOps.exif_transpose(image).convert("RGB")
            output = io.BytesIO()
            photo.save(output, format="JPEG", quality=90, optimize=True)
    except ValidationAppError:
        raise
    except Exception as exc:
        raise ValidationAppError(
            "Nie udało się odczytać zdjęcia. Zapisz je jako JPG i spróbuj ponownie.",
            code="IMAGE_UNREADABLE",
        ) from exc
    return output.getvalue()


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

    converted = extension in CONVERTED_TO_JPEG
    if converted:
        content = _heic_to_jpeg(content)
        extension, mime_type = "jpg", "image/jpeg"

    checksum = hashlib.sha256(content).hexdigest()
    return ValidatedUpload(
        content=content,
        extension=extension,
        mime_type=mime_type,
        checksum=checksum,
        converted=converted,
    )
