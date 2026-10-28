"""The office's logo on its clients' request pages and in their emails.

Any PNG, JPG or WebP up to a few MB is read, turned the way it was taken,
shrunk to fit and saved again as a PNG - what we serve is always our own
re-encoding, never the uploaded bytes. Shown while the account's plan is a
paid one (the trial included); on Free it stays stored, just not shown."""

import io
import secrets

from django.db import transaction
from django.urls import reverse

from apps.accounts.models import AccountLogo
from apps.common.exceptions import ValidationAppError
from apps.common.site import absolute_url

MAX_UPLOAD_BYTES = 3 * 1024 * 1024
MAX_PIXELS = 25_000_000
# Room for a wide logo; pages show it at most 56 px high.
MAX_WIDTH, MAX_HEIGHT = 720, 240
FORMATS = {"PNG", "JPEG", "WEBP"}
# How high emails show it.
EMAIL_HEIGHT = 48


def _png(uploaded):
    from PIL import Image, ImageOps

    if uploaded.size > MAX_UPLOAD_BYTES:
        raise ValidationAppError(
            "Plik z logo może mieć najwyżej 3 MB.", code="LOGO_TOO_LARGE"
        )
    content = uploaded.read()
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in FORMATS:
                raise ValidationAppError(
                    "Logo musi być plikiem PNG, JPG albo WebP.", code="LOGO_FORMAT"
                )
            if image.width * image.height > MAX_PIXELS:
                raise ValidationAppError(
                    "Logo ma zbyt dużą rozdzielczość.", code="LOGO_TOO_LARGE"
                )
            logo = ImageOps.exif_transpose(image).convert("RGBA")
    except ValidationAppError:
        raise
    except Exception as exc:
        raise ValidationAppError(
            "Nie udało się odczytać pliku. Wybierz logo w formacie PNG albo JPG.",
            code="LOGO_UNREADABLE",
        ) from exc
    # Transparent margins only take room.
    box = logo.getbbox()
    if box is None:
        raise ValidationAppError("Logo jest puste.", code="LOGO_EMPTY")
    logo = logo.crop(box)
    logo.thumbnail((MAX_WIDTH, MAX_HEIGHT))
    output = io.BytesIO()
    logo.save(output, format="PNG", optimize=True)
    return output.getvalue(), logo.width, logo.height


@transaction.atomic
def save_logo(user, uploaded):
    image, width, height = _png(uploaded)
    AccountLogo.objects.update_or_create(
        user=user,
        defaults={
            "image": image,
            "width": width,
            "height": height,
            "key": secrets.token_urlsafe(16),
        },
    )


def remove_logo(user):
    AccountLogo.objects.filter(user=user).delete()


def logo_of(user):
    return AccountLogo.objects.filter(user=user).only("key", "width", "height").first()


def shown(user):
    """Whether clients see the account's logo now: on a paid plan."""
    from apps.billing.services import plan_for

    plan, _ = plan_for(user)
    return plan.is_paid


def logo_for_clients(user):
    """{"path", "url", "width", "height"} - the logo as emails and the
    client's page show it - or None."""
    logo = logo_of(user)
    if logo is None or not shown(user):
        return None
    scale = EMAIL_HEIGHT / logo.height if logo.height > EMAIL_HEIGHT else 1
    path = reverse("accounts:logo", args=[logo.key])
    return {
        # Pages use the path, emails the full address.
        "path": path,
        "url": absolute_url(path),
        "width": round(logo.width * scale),
        "height": round(logo.height * scale),
    }
