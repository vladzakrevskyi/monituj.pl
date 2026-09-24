"""Generates the favicons and the social preview images (Open Graph).

    .venv/bin/python scripts/brand_images.py

Needs Pillow (requirements/dev.txt) and a bold sans font with Polish
letters: Arial on macOS, DejaVu Sans on Linux, or MONITUJ_FONT=/path.ttf.
The results are committed to static/images/, so the server never runs this.
"""

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BRAND_DIR = ROOT / "static" / "images" / "brand"
OG_DIR = ROOT / "static" / "images" / "og"

ORANGE = "#ff6b00"
BLACK = "#0b0b0c"
WHITE = "#ffffff"
MUTED = "#b4b5bd"
LINE = "#26262b"

BOLD_FONTS = [
    os.environ.get("MONITUJ_FONT", ""),
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
REGULAR_FONTS = [
    os.environ.get("MONITUJ_FONT_REGULAR", ""),
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def font(size, bold=True):
    for path in BOLD_FONTS if bold else REGULAR_FONTS:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size)
    raise SystemExit("No font with Polish letters found - set MONITUJ_FONT.")


# --- the mark: orange rounded square with a black "M" -----------------------


def mark(size, radius_ratio=0.22, padding_ratio=0.0, background=None):
    scale = 4  # draw big, scale down: smooth edges at every size
    big = size * scale
    image = Image.new("RGBA", (big, big), background or (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    pad = int(big * padding_ratio)
    box = (pad, pad, big - pad, big - pad)
    draw.rounded_rectangle(box, radius=int((big - 2 * pad) * radius_ratio), fill=ORANGE)
    letter = font(int((big - 2 * pad) * 0.62))
    left, top, right, bottom = draw.textbbox((0, 0), "M", font=letter)
    x = (big - (right - left)) / 2 - left
    y = (big - (bottom - top)) / 2 - top
    draw.text((x, y), "M", font=letter, fill=BLACK)
    return image.resize((size, size), Image.LANCZOS)


FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="#ff6b00"/>
<path fill="#0b0b0c"
 d="M16 46V18h7.4l8.6 15.2L40.6 18H48v28h-6.6V29.6L34.2 42h-4.4l-7.2-12.4V46z"/>
</svg>
"""


def favicons():
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    (BRAND_DIR / "favicon.svg").write_text(FAVICON_SVG)
    mark(48).save(BRAND_DIR / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    mark(32).save(BRAND_DIR / "favicon-32.png")
    mark(192).save(BRAND_DIR / "icon-192.png")
    mark(512).save(BRAND_DIR / "icon-512.png")
    # Maskable: the system may cut the corners, so the mark keeps a margin.
    mark(512, radius_ratio=0.18, padding_ratio=0.12, background=BLACK).save(
        BRAND_DIR / "icon-maskable-512.png"
    )
    # iOS draws its own rounded corners and dislikes transparency.
    mark(180, radius_ratio=0, background=ORANGE).convert("RGB").save(
        BRAND_DIR / "apple-touch-icon.png"
    )


# --- social previews (1200 x 630) -------------------------------------------

W, H = 1200, 630
LEFT = 80


def wrap(draw, text, face, width):
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=face) <= width:
            line = candidate
        else:
            lines.append(line)
            line = word
    lines.append(line)
    return lines


STATUSES = [
    ("Zaakceptowany", "#e6f4ea", "#15803d"),
    ("Zaakceptowany", "#e6f4ea", "#15803d"),
    ("Dostarczony", "#fdf3d7", "#a15c07"),
    ("Brak", "#fdecec", "#c81e1e"),
]


def checklist_card(image, title, items):
    draw = ImageDraw.Draw(image)
    x0, y0, x1 = 770, 150, 1130
    row_h = 58
    y1 = y0 + 78 + row_h * len(items) + 50
    draw.rounded_rectangle((x0, y0, x1, y1), radius=22, fill=WHITE)
    draw.text((x0 + 26, y0 + 24), title, font=font(24), fill=BLACK)
    face = font(19, bold=False)
    badge_face = font(15)
    y = y0 + 78
    for index, name in enumerate(items):
        label, background, color = STATUSES[min(index, len(STATUSES) - 1)]
        draw.line((x0 + 26, y, x1 - 26, y), fill="#e4e4e8", width=2)
        short = name if draw.textlength(name, font=face) < 170 else name[:17] + "…"
        draw.text((x0 + 26, y + 18), short, font=face, fill="#3f3f46")
        badge_w = draw.textlength(label, font=badge_face) + 28
        draw.rounded_rectangle(
            (x1 - 26 - badge_w, y + 14, x1 - 26, y + 44), radius=15, fill=background
        )
        draw.text((x1 - 26 - badge_w + 14, y + 20), label, font=badge_face, fill=color)
        y += row_h
    draw.text(
        (x0 + 26, y + 12),
        "Następne przypomnienie: jutro 14:20",
        font=font(16, bold=False),
        fill="#62636d",
    )


def og_image(name, eyebrow, headline, sub, card_title, items):
    image = Image.new("RGB", (W, H), BLACK)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 12, H), fill=ORANGE)

    image.paste(mark(56), (LEFT, 60), mark(56))
    draw.text((LEFT + 74, 68), "Monituj", font=font(36), fill=WHITE)

    y = 170
    draw.text((LEFT, y), eyebrow.upper(), font=font(20), fill=ORANGE)
    y += 44
    head_face = font(54)
    for line in wrap(draw, headline, head_face, 620)[:4]:
        draw.text((LEFT, y), line, font=head_face, fill=WHITE)
        y += 64
    y += 14
    sub_face = font(24, bold=False)
    for line in wrap(draw, sub, sub_face, 620)[:3]:
        draw.text((LEFT, y), line, font=sub_face, fill=MUTED)
        y += 34

    draw.line((LEFT, H - 78, 700, H - 78), fill=LINE, width=2)
    draw.text((LEFT, H - 60), "monituj.pl", font=font(22), fill=WHITE)
    draw.text(
        (LEFT + 150, H - 58),
        "Przestań gonić klientów o dokumenty",
        font=font(20, bold=False),
        fill=MUTED,
    )

    checklist_card(image, card_title, items)
    image.save(OG_DIR / f"{name}.png", optimize=True)


MONTHLY = ["Faktury sprzedaży", "Faktury kosztowe", "Wyciąg bankowy", "Raport kasowy"]

PAGES = [
    (
        "default",
        "Zbieranie dokumentów od klientów",
        "Przestań gonić klientów o dokumenty",
        "Monituj wysyła listę, sam przypomina o brakach i pilnuje terminów.",
        "Dokumenty za wrzesień",
        MONTHLY,
    ),
    (
        "landing",
        "Zbieranie dokumentów od klientów",
        "Przestań gonić klientów o dokumenty",
        "Monituj wysyła listę, sam przypomina o brakach i pilnuje terminów.",
        "Dokumenty za wrzesień",
        MONTHLY,
    ),
    (
        "jak-to-dziala",
        "Jak to działa",
        "Od prośby do kompletu dokumentów w 4 krokach",
        "Lista, link dla klienta, automatyczne przypomnienia i akceptacja.",
        "Dokumenty za wrzesień",
        MONTHLY,
    ),
    (
        "funkcje",
        "Funkcje",
        "Przypomnienia, statusy i lista braków w jednym miejscu",
        "Klient przesyła pliki bez konta, Ty widzisz, czego brakuje.",
        "Dokumenty za wrzesień",
        MONTHLY,
    ),
    (
        "dla-kogo",
        "Dla kogo",
        "Dla firm, w których praca czeka na dokumenty",
        "Biura rachunkowe, kadry, kancelarie, pośrednicy i firmy B2B.",
        "Akta nowego pracownika",
        [
            "Kwestionariusz osobowy",
            "Świadectwo pracy",
            "Badania lekarskie",
            "Szkolenie BHP",
        ],
    ),
    (
        "poradnik",
        "Poradnik",
        "Jak zbierać dokumenty od klientów i ich nie gonić",
        "Sześć zasad, dzięki którym dokumenty przychodzą na czas.",
        "Dokumenty za wrzesień",
        MONTHLY,
    ),
    (
        "bezpieczenstwo",
        "Bezpieczeństwo i RODO",
        "Dokumenty klientów bezpieczne i pod kontrolą",
        "Unikalne linki, hasła, prywatny magazyn i automatyczne usuwanie plików.",
        "Wniosek kredytowy",
        [
            "Zaświadczenie o dochodach",
            "Wyciągi z konta",
            "Umowa przedwstępna",
            "Akt notarialny",
        ],
    ),
    (
        "cennik",
        "Cennik",
        "Monituj za darmo – bez karty kredytowej",
        "Prośby o dokumenty, przypomnienia i panel z brakami.",
        "Dokumenty za wrzesień",
        MONTHLY,
    ),
    (
        "faq",
        "Najczęstsze pytania",
        "Pytania o zbieranie dokumentów od klientów",
        "Przypomnienia, konto klienta, bezpieczeństwo i koszty.",
        "Dokumenty za wrzesień",
        MONTHLY,
    ),
    (
        "demo",
        "Demo",
        "Wypróbuj Monituj bez rejestracji",
        "Własne konto demonstracyjne z przykładowymi danymi – w jedno kliknięcie.",
        "Zamknięcie roku 2025",
        ["Bilans", "Rachunek zysków", "Inwentaryzacja", "Zestawienie środków"],
    ),
    (
        "wyslij-prosbe",
        "Bez zakładania konta",
        "Wyślij prośbę o dokumenty w 2 minuty",
        "Lista, termin i automatyczne przypomnienia – bez rejestracji.",
        "Dokumenty do umowy",
        ["Dowód osobisty", "Odpis z KRS", "Pełnomocnictwo", "Potwierdzenie przelewu"],
    ),
]


def segment_pages():
    import sys

    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    import django

    django.setup()
    from apps.common.content import SEGMENTS

    return [
        (
            f"segment-{segment['slug']}",
            segment["title"],
            segment["h1"],
            segment["teaser"],
            "Przykładowa prośba",
            segment["checklist"][:4],
        )
        for segment in SEGMENTS
    ]


def main():
    favicons()
    OG_DIR.mkdir(parents=True, exist_ok=True)
    for page in PAGES + segment_pages():
        og_image(*page)
    print(f"Saved icons to {BRAND_DIR} and previews to {OG_DIR}")


if __name__ == "__main__":
    main()
