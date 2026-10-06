"""The promo film on the home page and "Jak to działa": its files, length and
chapters. Two cuts of the same film - wide (16:9) and tall (9:16, for phones
held upright) - so each chapter starts at its own second in each."""

from django.templatetags.static import static

from apps.common.site import absolute_url

WIDE = "video/monituj-promo-16x9.mp4"
TALL = "video/monituj-promo-9x16.mp4"
WIDE_POSTER = "video/monituj-promo-16x9.jpg"
TALL_POSTER = "video/monituj-promo-9x16.jpg"
THUMB = "video/monituj-promo-thumb.jpg"  # the hero card: a still from the panel
TITLE = "Monituj w dwie minuty"
DESCRIPTION = (
    "Jak zacząć z Monituj: zakładasz konto, dodajesz klientów, wysyłasz prośbę "
    "o dokumenty z gotowego szablonu, klient przesyła pliki bez zakładania "
    "konta, a Ty akceptujesz je w panelu - razem z zespołem."
)
PUBLISHED = "2026-10-06"
SECONDS = 130
# (label, start in the wide cut, start in the tall cut), seconds.
CHAPTERS = [
    ("Konto", 0, 0),
    ("Klienci", 21.8, 22.4),
    ("Prośba", 39.6, 40.8),
    ("Klient", 81.0, 83.2),
    ("Panel", 96.0, 98.3),
    ("Zespół", 105.3, 107.7),
]


def minutes_label():
    return f"{round(SECONDS / 60)} min"


def iso_duration():
    minutes, seconds = divmod(SECONDS, 60)
    return f"PT{minutes}M{seconds}S"


def video_object():
    """schema.org VideoObject - lets the film show up in search results."""
    return {
        "@type": "VideoObject",
        "name": TITLE,
        "description": DESCRIPTION,
        "thumbnailUrl": absolute_url(static(WIDE_POSTER)),
        "contentUrl": absolute_url(static(WIDE)),
        "uploadDate": PUBLISHED,
        "duration": iso_duration(),
        "inLanguage": "pl-PL",
        "publisher": {"@id": absolute_url("/#organization")},
    }
