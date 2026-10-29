"""Photos can't take the server's memory (apps/documents/images.py): the
size is checked from the header, JPEGs are decoded shrunk, whole decodes
take turns."""

import io
import re

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections
from PIL import Image

from apps.common.exceptions import ValidationAppError
from apps.documents import images, pages
from apps.documents.validation import validate_upload


def _image(name, fmt, size=(40, 20), mode="RGB", exif=None):
    buffer = io.BytesIO()
    extra = {"exif": exif} if exif is not None else {}
    Image.new(mode, size, 128).save(buffer, format=fmt, **extra)
    return SimpleUploadedFile(name, buffer.getvalue())


def _heic(size=(40, 20)):
    import pillow_heif

    pillow_heif.register_heif_opener()
    return _image("zdjecie.heic", "HEIF", size)


def _pdf_page_size(pdf_upload):
    """The first page in pixels, from its /MediaBox (points at 200 dpi)."""
    found = re.search(rb"/MediaBox \[ ?0 0 ([\d.]+) ([\d.]+) ?\]", pdf_upload.read())
    return tuple(
        round(float(value) * pages.PAGE_RESOLUTION / 72) for value in found.groups()
    )


def test_the_png_from_the_audit_is_refused_before_decoding():
    # 13000 x 13000 px in 1-bit colour: a tiny file, 169 megapixels.
    bomb = _image("strona.png", "PNG", size=(13000, 13000), mode="1")
    assert bomb.size < 300_000

    with pytest.raises(ValidationAppError) as exc_info:
        pages.photos_to_pdf([bomb], "Wyciąg")
    assert exc_info.value.code == "IMAGE_TOO_LARGE"


def test_a_jpeg_may_be_far_bigger_than_a_png(monkeypatch):
    monkeypatch.setattr(images, "MAX_PIXELS", 100)

    pdf = pages.photos_to_pdf([_image("strona.jpg", "JPEG")], "Wyciąg")
    assert pdf.name == "Wyciąg (1 str.).pdf"

    with pytest.raises(ValidationAppError) as exc_info:
        pages.photos_to_pdf([_image("strona.png", "PNG")], "Wyciąg")
    assert exc_info.value.code == "IMAGE_TOO_LARGE"


def test_a_jpeg_has_a_limit_too(monkeypatch):
    monkeypatch.setattr(images, "MAX_JPEG_PIXELS", 100)

    with pytest.raises(ValidationAppError) as exc_info:
        pages.photos_to_pdf([_image("strona.jpg", "JPEG")], "Wyciąg")
    assert exc_info.value.code == "IMAGE_TOO_LARGE"


def test_a_big_jpeg_page_is_shrunk_to_the_page_size(monkeypatch):
    monkeypatch.setattr(pages, "PAGE_LONG_SIDE", 100)

    pdf = pages.photos_to_pdf([_image("strona.jpg", "JPEG", (800, 400))], "Wyciąg")

    assert max(_pdf_page_size(pdf)) <= 100


def test_a_page_is_turned_the_way_it_was_taken():
    exif = Image.Exif()
    exif[0x0112] = 6  # taken with the phone turned: rotate 90 degrees
    photo = _image("strona.jpg", "JPEG", (40, 20), exif=exif.tobytes())

    pdf = pages.photos_to_pdf([photo], "Wyciąg")

    width, height = _pdf_page_size(pdf)
    assert height > width


def test_a_broken_photo_is_a_clear_error_not_a_crash():
    broken = SimpleUploadedFile("strona.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 200)

    with pytest.raises(ValidationAppError) as exc_info:
        pages.photos_to_pdf([broken], "Wyciąg")
    assert exc_info.value.code in {"IMAGE_UNREADABLE", "MIME_NOT_ALLOWED"}


@pytest.mark.django_db
def test_a_too_big_heic_is_refused(monkeypatch):
    monkeypatch.setattr(images, "MAX_PIXELS", 100)

    with pytest.raises(ValidationAppError) as exc_info:
        validate_upload(_heic())
    assert exc_info.value.code == "IMAGE_TOO_LARGE"


@pytest.mark.django_db
def test_a_heic_photo_still_becomes_a_jpg():
    result = validate_upload(_heic())

    assert (result.extension, result.mime_type) == ("jpg", "image/jpeg")


@pytest.mark.django_db(transaction=True)
def test_whole_decodes_take_turns(monkeypatch):
    monkeypatch.setattr(images, "WAIT_SECONDS", 0.3)
    other = connections.create_connection("default")
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [images.LOCK_KEY])

        with pytest.raises(ValidationAppError) as exc_info:
            validate_upload(_heic())
        assert exc_info.value.code == "SERVER_BUSY"

        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [images.LOCK_KEY])
        assert validate_upload(_heic()).extension == "jpg"
    finally:
        other.close()


@pytest.mark.django_db(transaction=True)
def test_the_turn_is_given_back_after_an_error():
    with pytest.raises(RuntimeError), images.one_at_a_time():
        raise RuntimeError("decoding failed")

    with connections["default"].cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [images.LOCK_KEY])
        assert cursor.fetchone()[0]
        cursor.execute("SELECT pg_advisory_unlock(%s)", [images.LOCK_KEY])
