"""The promo film: its own page (/film/, the one search engines index), the
home page and "Jak to działa". Its files, length and chapters. Two cuts of the
same film - wide (16:9) and tall (9:16, for phones held upright) - so each
chapter starts at its own second in each."""

from django.conf import settings
from django.urls import reverse

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
# When the film first went out. Stays as it is when the film is re-cut: Google
# asks for the first publication, with the time zone.
PUBLISHED = "2026-10-06T12:53:00+02:00"
SECONDS = 255
# (label, start in the wide cut, start in the tall cut, what it shows), seconds.
CHAPTERS = [
    (
        "Konto",
        0,
        0,
        "Zakładasz konto przez Google albo e-mailem, 30 dni za darmo i bez karty. "
        "Dodajesz logo, a podgląd obok pokazuje, jak zobaczy to klient.",
    ),
    (
        "Klienci",
        29.0,
        29.9,
        "Dodajesz klienta ręcznie - nazwa i e-mail wystarczą. Masz ich więcej? "
        "Importujesz wszystkich z Excela albo programu księgowego.",
    ),
    (
        "Prośba",
        46.8,
        47.4,
        "Zaczynasz od gotowego szablonu, dopisujesz brakujące dokumenty, wybierasz "
        "klientów i termin. Każdy klient dostaje mail z własnym linkiem.",
    ),
    (
        "Klient",
        87.3,
        88.8,
        "Klient przesyła pliki bez zakładania konta. Kilka zdjęć stron łączymy w "
        "jeden PDF, a dokument spoza listy klient dodaje sam, z opisem.",
    ),
    (
        "Panel",
        120.4,
        121.9,
        "W panelu widzisz, co czeka na Ciebie i co jest po terminie. Akceptujesz "
        "dokumenty jednym kliknięciem, a o brakach przypominamy klientowi sami.",
    ),
    (
        "Zestawienie",
        138.2,
        140.9,
        "Zestawienie pokazuje, kto ma komplet, a komu czegoś brakuje. Jednym "
        "kliknięciem przypominasz wszystkim, którym czegoś brakuje.",
    ),
    (
        "Pytanie",
        149.3,
        152.1,
        "Coś jest niejasne na wyciągu? Pytasz klienta i dopytujesz w tej samej "
        "rozmowie, a cała historia zostaje w jednym miejscu.",
    ),
    (
        "Karta klienta",
        189.6,
        193.1,
        "Wszystko o kliencie na jednej stronie: notatki zespołu i przypomnienia o "
        "tym, o czym nie chcesz zapomnieć.",
    ),
    (
        "Kalendarz",
        206.0,
        207.7,
        "Terminy klientów, pytania i Twoje przypomnienia w jednym widoku. Rano "
        "dostajesz mail „Na dziś”, a kalendarz dodasz też do telefonu.",
    ),
    (
        "Zespół",
        230.6,
        231.4,
        "Zapraszasz współpracowników. Każdy ma własny login i od razu pracuje na "
        "tych samych klientach, pytaniach i kalendarzu.",
    ),
]


def stable_url(path):
    """A file's address without the content hash: it stays the same when the
    film is re-cut, as Google asks for. Hashed addresses 404 after each one."""
    return f"{settings.STATIC_URL}{path}"


def clock(seconds):
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes}:{rest:02d}"


def chapters():
    """The chapters for templates and markup; `second` is the whole second a
    link to the chapter opens at (/film/?t=29)."""
    return [
        {
            "number": number,
            "label": label,
            "wide": wide,
            "tall": tall,
            "summary": summary,
            "second": int(wide),
            "clock": clock(wide),
        }
        for number, (label, wide, tall, summary) in enumerate(CHAPTERS, start=1)
    ]


def minutes_label():
    return f"{round(SECONDS / 60)} min"


def iso_duration():
    minutes, seconds = divmod(SECONDS, 60)
    return f"PT{minutes}M{seconds}S"


def _clips():
    page = absolute_url(reverse("pages:film"))
    items = chapters()
    ends = [item["second"] for item in items[1:]] + [SECONDS]
    return [
        {
            "@type": "Clip",
            "name": item["label"],
            "startOffset": item["second"],
            "endOffset": end,
            "url": f"{page}?t={item['second']}",
        }
        for item, end in zip(items, ends, strict=True)
    ]


def video_object():
    """schema.org VideoObject - lets the film show up in search results. Only
    on /film/: Google indexes a video on a page whose main purpose is to show
    it, and the other pages only carry the film alongside their text."""
    return {
        "@type": "VideoObject",
        "name": TITLE,
        "description": DESCRIPTION,
        "thumbnailUrl": absolute_url(stable_url(WIDE_POSTER)),
        "contentUrl": absolute_url(stable_url(WIDE)),
        "uploadDate": PUBLISHED,
        "duration": iso_duration(),
        "inLanguage": "pl-PL",
        "publisher": {"@id": absolute_url("/#organization")},
        "hasPart": _clips(),
    }


def sitemap_video():
    """The same film in the words of the video sitemap."""
    return {
        "thumbnail": absolute_url(stable_url(WIDE_POSTER)),
        "title": TITLE,
        "description": DESCRIPTION,
        "content": absolute_url(stable_url(WIDE)),
        "duration": SECONDS,
        "published": PUBLISHED,
    }
