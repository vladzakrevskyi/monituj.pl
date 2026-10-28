"""Photos of a document's pages as one PDF - "Zrób zdjęcia stron".

A client photographs a five-page bank statement with their phone; the
sender gets one PDF, pages in the order they were taken, not five JPGs.
Each photo goes through the same checks as any upload, is turned the way it
was taken and shrunk to a sensible size; the PDF then goes through the
ordinary upload (apps/documents/services.py)."""

import io
import re

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.common.exceptions import ValidationAppError
from apps.documents.validation import MAX_UPLOAD_SIZE, validate_upload

MAX_PAGES = 15
# A page's longer side, in pixels - an A4 at about 200 dpi, sharp to read.
PAGE_LONG_SIDE = 2200
PAGE_RESOLUTION = 200
PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "heic", "heif"}


def _page(uploaded):
    from PIL import Image, ImageOps

    validated = validate_upload(uploaded)
    if validated.extension not in PHOTO_EXTENSIONS:
        raise ValidationAppError(
            "Do PDF-a połączymy tylko zdjęcia (JPG, PNG albo z iPhone'a). "
            "Inne pliki prześlij przyciskiem „Wybierz plik”.",
            code="PAGE_NOT_A_PHOTO",
        )
    with Image.open(io.BytesIO(validated.content)) as image:
        page = ImageOps.exif_transpose(image).convert("RGB")
    page.thumbnail((PAGE_LONG_SIDE, PAGE_LONG_SIDE))
    return page


def file_name(item_name, pages):
    """'Wyciągi bankowe (3 str.).pdf' - safe in any download."""
    base = re.sub(r'[\\/:*?"<>|]+', " ", item_name).strip()[:80] or "Dokument"
    return f"{base} ({pages} str.).pdf"


def photos_to_pdf(files, item_name):
    if not files:
        raise ValidationAppError(
            "Zrób zdjęcie co najmniej jednej strony.", code="NO_PAGES"
        )
    if len(files) > MAX_PAGES:
        raise ValidationAppError(
            f"Połączymy najwyżej {MAX_PAGES} stron. Podziel dokument na części.",
            code="TOO_MANY_PAGES",
        )
    pages = [_page(uploaded) for uploaded in files]
    output = io.BytesIO()
    pages[0].save(
        output,
        format="PDF",
        save_all=True,
        append_images=pages[1:],
        resolution=PAGE_RESOLUTION,
        quality=85,
    )
    content = output.getvalue()
    if len(content) > MAX_UPLOAD_SIZE:
        raise ValidationAppError(
            "Z tych zdjęć wychodzi za duży plik. Prześlij dokument w dwóch częściach.",
            code="PDF_TOO_LARGE",
        )
    return SimpleUploadedFile(
        file_name(item_name, len(pages)), content, content_type="application/pdf"
    )
