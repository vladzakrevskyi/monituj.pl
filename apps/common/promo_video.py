"""The promo film on the home page and "Jak to działa": its files, length and
chapters. Two cuts of the same film - wide (16:9) and tall (9:16, for phones
held upright) - so each chapter starts at its own second in each."""

from django.templatetags.static import static

from apps.common.site import absolute_url

WIDE = "video/monituj-promo-16x9.mp4"
TALL = "video/monituj-promo-9x16.mp4"
WIDE_POSTER = "video/monituj-promo-16x9.jpg"
TALL_POSTER = "video/monituj-promo-9x16.jpg"
THUMB = "video/monituj-promo-thumb.jpg"  # the hero card: a still from the calendar
TITLE = "Monituj w trzy minuty"
DESCRIPTION = (
    "Jak zacząć z Monituj: zakładasz konto, dodajesz klientów, wysyłasz prośbę "
    "o dokumenty z gotowego szablonu, klient przesyła pliki bez zakładania "
    "konta, a Ty akceptujesz je w panelu. Zadajesz klientowi pytanie z "
    "notatką, po co pytasz, masz wszystko o kliencie na jego karcie, a "
    "terminy i przypomnienia w kalendarzu - razem z zespołem."
)
PUBLISHED = "2026-10-25"
SECONDS = 194
# (label, start in the wide cut, start in the tall cut), seconds.
CHAPTERS = [
    ("Konto", 0, 0),
    ("Klienci", 21.8, 22.5),
    ("Prośba", 39.4, 40.6),
    ("Klient", 79.8, 82.4),
    ("Panel", 94.6, 97.3),
    ("Pytanie", 103.0, 105.7),
    ("Karta klienta", 127.5, 130.7),
    ("Kalendarz", 144.0, 145.4),
    ("Zespół", 168.5, 170.4),
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
