import hashlib
import io
import os
import zipfile

import magic

from apps.common.exceptions import ValidationAppError
from apps.documents import antivirus, images

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
    is left out. HEIC is decoded whole - with the size checked first and one
    such decode at a time (apps/documents/images.py)."""
    import pillow_heif
    from PIL import Image, ImageOps

    pillow_heif.register_heif_opener()
    try:
        with Image.open(io.BytesIO(content)) as image:
            images.check_size(image)
            with images.one_at_a_time():
                image.load()
                # In place: no extra copies of a half-gigabyte picture.
                photo = image if image.mode == "RGB" else image.convert("RGB")
                ImageOps.exif_transpose(photo, in_place=True)
                output = io.BytesIO()
                photo.save(output, format="JPEG", quality=90, optimize=True)
    except ValidationAppError:
        raise
    except Image.DecompressionBombError as exc:
        raise images.too_large() from exc
    except Exception as exc:
        raise images.unreadable() from exc
    return output.getvalue()


OFFICE_ZIPS = {"docx", "xlsx"}
DAMAGED_MESSAGE = (
    "Plik jest uszkodzony albo nie jest dokumentem Office. Otwórz go i zapisz "
    "ponownie albo wyślij jako PDF."
)


def _check_office_zip(content):
    """A .docx / .xlsx is a zip with Office's own structure - not just any
    zip renamed - and without a macro project (Word and Excel refuse those
    in .docx / .xlsx anyway, so it can only be a trick)."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile as exc:
        raise ValidationAppError(DAMAGED_MESSAGE, code="FILE_DAMAGED") from exc
    if "[Content_Types].xml" not in names:
        raise ValidationAppError(DAMAGED_MESSAGE, code="FILE_DAMAGED")
    if any(name.lower().endswith("vbaproject.bin") for name in names):
        raise ValidationAppError(antivirus.MACROS_MESSAGE, code="FILE_HAS_MACROS")


def validate_upload(uploaded_file, request_obj=None) -> ValidatedUpload:
    """request_obj: where the file is going - named in an antivirus alarm."""
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

    if extension in OFFICE_ZIPS:
        _check_office_zip(content)
    # Before anything decodes it (HEIC below, photos in pages.py).
    antivirus.check(content, safe_name, request_obj)

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
