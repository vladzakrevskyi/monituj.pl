"""Decoding photos without letting one file take the server's memory.

On disk a photo is small; decoded, it takes width x height x 3 bytes - a
187 KB PNG of 169 megapixels needed almost 900 MB. So:
- the size is read from the file's header, before a single pixel is
  decoded, and refused above the limit of its format;
- a JPEG is decoded already shrunk where a smaller picture is enough
  (thumbnail() does it with Image.draft): a phone's 200-megapixel photo
  then takes tens of MB, so JPEGs may be that big;
- HEIC and PNG can't be decoded shrunk (a 48-megapixel iPhone photo needs
  about half a GB), so such decoding takes turns: one at a time on the
  whole server, the others wait a moment (one_at_a_time).
"""

import time
from contextlib import contextmanager

from django.db import connection

from apps.common.exceptions import ValidationAppError

# iPhones take up to 48 megapixels, screenshots a few.
MAX_PIXELS = 50_000_000
# Phones with 200-megapixel cameras save JPEGs.
MAX_JPEG_PIXELS = 300_000_000
TOO_LARGE_MESSAGE = "Zdjęcie ma zbyt dużą rozdzielczość."
UNREADABLE_MESSAGE = (
    "Nie udało się odczytać zdjęcia. Zapisz je jako JPG i spróbuj ponownie."
)
BUSY_MESSAGE = "Przetwarzamy teraz inne zdjęcia. Spróbuj ponownie za chwilę."
# Any constant; the same for every process.
LOCK_KEY = 7_201_903_115
WAIT_SECONDS = 60
POLL_SECONDS = 0.2


def configure_pillow():
    """Pillow's own guard against decompression bombs - above our limits,
    so it only catches what got past them (DocumentsConfig.ready)."""
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = MAX_JPEG_PIXELS


def check_size(image):
    """Refuses an opened (not yet decoded) image above its format's limit."""
    limit = MAX_JPEG_PIXELS if image.format == "JPEG" else MAX_PIXELS
    if image.width * image.height > limit:
        raise ValidationAppError(TOO_LARGE_MESSAGE, code="IMAGE_TOO_LARGE")


def too_large():
    return ValidationAppError(TOO_LARGE_MESSAGE, code="IMAGE_TOO_LARGE")


def unreadable():
    return ValidationAppError(UNREADABLE_MESSAGE, code="IMAGE_UNREADABLE")


@contextmanager
def one_at_a_time():
    """A whole decode at a time on the server: a PostgreSQL advisory lock,
    shared by every web process and released even if one of them dies."""
    if connection.vendor != "postgresql":
        yield
        return
    deadline = time.monotonic() + WAIT_SECONDS
    with connection.cursor() as cursor:
        while True:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_KEY])
            if cursor.fetchone()[0]:
                break
            if time.monotonic() > deadline:
                raise ValidationAppError(BUSY_MESSAGE, code="SERVER_BUSY")
            time.sleep(POLL_SECONDS)
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_KEY])
