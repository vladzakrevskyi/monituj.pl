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
TITLE = "Monituj w kilka minut"
DESCRIPTION = (
    "Jak zacząć z Monituj: zakładasz konto i dodajesz logo, dodajesz klientów, "
    "wysyłasz prośbę o dokumenty z gotowego szablonu. Klient przesyła pliki "
    "bez zakładania konta - kilka zdjęć stron łączymy w jeden PDF, a dokument "
    "spoza listy dodaje sam - a Ty akceptujesz je w panelu. W zestawieniu "
    "widzisz, kto ma komplet, i jednym kliknięciem przypominasz reszcie. "
    "Zadajesz klientowi pytanie i dopytujesz w tej samej rozmowie, masz "
    "wszystko o kliencie na jego karcie, a terminy w kalendarzu - razem z "
    "zespołem."
)
PUBLISHED = "2026-10-31"
SECONDS = 255
# (label, start in the wide cut, start in the tall cut), seconds.
CHAPTERS = [
    ("Konto", 0, 0),
    ("Klienci", 29.0, 29.9),
    ("Prośba", 46.8, 47.4),
    ("Klient", 87.3, 88.8),
    ("Panel", 120.4, 121.9),
    ("Zestawienie", 138.2, 140.9),
    ("Pytanie", 149.3, 152.1),
    ("Karta klienta", 189.6, 193.1),
    ("Kalendarz", 206.0, 207.7),
    ("Zespół", 230.6, 231.4),
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
