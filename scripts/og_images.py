"""Generates the social preview images (Open Graph, 1200x630) in the site's
design: drawn as HTML with the site's own stylesheet and fonts, then
screenshotted.

    pip install playwright && playwright install chromium   # once
    .venv/bin/python scripts/og_images.py

The results are committed to static/images/og/, so the server never runs
this. Favicons stay in scripts/brand_images.py.
"""

# The page data and the inline HTML read better unwrapped.
# ruff: noqa: E501

import asyncio
import os
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OG_DIR = ROOT / "static" / "images" / "og"
STATIC = (ROOT / "static").as_uri()

MONTHLY = ["Wyciągi bankowe", "Faktury kosztowe", "Faktury sprzedaży", "Raport kasowy"]

# name, label, headline, its orange end, line under it, card title, card items
PAGES = [
    ("default", "Program do zbierania dokumentów", "Zbieranie dokumentów od klientów.", "Bez gonienia.",
     "Lista dokumentów, klient bez konta, przypomnienia o brakach.", "Dokumenty za wrzesień", MONTHLY),
    ("landing", "Program do zbierania dokumentów", "Zbieranie dokumentów od klientów.", "Bez gonienia.",
     "Lista dokumentów, klient bez konta, przypomnienia o brakach.", "Dokumenty za wrzesień", MONTHLY),
    ("jak-to-dziala", "Jak to działa", "Zbieranie dokumentów od klientów.", "Krok po kroku.",
     "Lista, jeden link dla klienta i automatyczne przypomnienia.", "Dokumenty za wrzesień", MONTHLY),
    ("funkcje", "Funkcje", "Funkcje programu do", "zbierania dokumentów.",
     "Przypomnienia, statusy, pytania do klienta i kalendarz.", "Dokumenty za wrzesień", MONTHLY),
    ("dla-kogo", "Dla kogo", "Program do zbierania dokumentów", "dla Twojej branży.",
     "Biura rachunkowe, kadry, kancelarie, kredyty i B2B.", "Akta nowego pracownika",
     ["Kwestionariusz osobowy", "Świadectwo pracy", "Badania lekarskie", "Szkolenie BHP"]),
    ("poradnik", "Poradnik", "Jak zbierać dokumenty od klientów", "i przestać ich gonić.",
     "Sześć zasad, dzięki którym dokumenty przychodzą na czas.", "Dokumenty za wrzesień", MONTHLY),
    ("bezpieczenstwo", "Bezpieczeństwo i RODO", "Bezpieczne przesyłanie dokumentów.", "Zgodnie z RODO.",
     "Szyfrowanie, unikalne linki i automatyczne usuwanie plików.", "Wniosek kredytowy",
     ["Zaświadczenie o dochodach", "Wyciągi z konta", "Umowa przedwstępna", "Akt notarialny"]),
    ("cennik", "Cennik", "Płacisz za dokumenty,", "na które czekasz.",
     "Plan Free za 0 zł. Płatne plany 30 dni za darmo, bez karty.", "Dokumenty za wrzesień", MONTHLY),
    ("faq", "Pytania", "Pytania o zbieranie", "dokumentów od klientów.",
     "Przypomnienia, klient bez konta, bezpieczeństwo i ceny.", "Dokumenty za wrzesień", MONTHLY),
    ("demo", "Demo", "Demo programu do zbierania dokumentów.", "Bez rejestracji.",
     "Własne konto demo z przykładowymi danymi, w jedno kliknięcie.", "Zamknięcie roku",
     ["Spis z natury", "Potwierdzenia sald", "Umowy leasingu", "Rachunek zysków"]),
    ("wyslij-prosbe", "Bez zakładania konta", "Prośba o dokumenty", "w 2 minuty.",
     "Lista, termin i automatyczne przypomnienia, bez rejestracji.", "Dokumenty do umowy",
     ["Dowód osobisty", "Odpis z KRS", "Pełnomocnictwo", "Potwierdzenie przelewu"]),
]  # fmt: skip


def segment_pages():
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    import django

    django.setup()
    from apps.common.content import SEGMENTS

    return [
        (
            f"segment-{s['slug']}",
            s["title"],
            s["h1"],
            s["h1_accent"],
            s["teaser"],
            "Lista dokumentów",
            s["checklist"][:4],
        )
        for s in SEGMENTS
    ]


def page(label, headline, accent, line, card_title, items):
    # Long headlines get smaller, so the line under them still fits.
    size = 60 if len(headline + accent) <= 48 else 50
    rows = "".join(
        f'<li><span><i class="lp-tick"></i>{escape(item)}</span></li>' for item in items
    )
    return f"""<!doctype html><html lang="pl"><head><meta charset="utf-8">
<link rel="stylesheet" href="{STATIC}/css/marketing.css">
<style>
*{{box-sizing:border-box}} html,body{{margin:0;width:1200px;height:630px;overflow:hidden}}
.og{{position:relative;display:grid;grid-template-columns:1fr 400px;gap:56px;align-items:center;
  width:1200px;height:630px;padding:56px 64px;background:var(--lp-black);color:#fff}}
.og::before{{content:"";position:absolute;inset:0;background-image:linear-gradient(to right,var(--lp-line-dark) 1px,transparent 1px);background-size:200px 100%;opacity:.55}}
.og>*{{position:relative}}
.og__logo img{{height:40px;display:block}}
.og h1{{margin:22px 0 20px;font-family:var(--lp-display);font-size:{size}px;font-weight:600;line-height:.98;letter-spacing:-.04em}}
.og h1 em{{font-style:normal;color:var(--lp-orange)}}
.og .lp-label{{color:#fff;margin-top:40px}}
.og p.line{{margin:0;font-size:22px;line-height:1.4;max-width:560px}}
.og>.og__site{{position:absolute;left:64px;bottom:40px;font-family:var(--lp-mono);font-size:16px;letter-spacing:.08em}}
.og .lp-card{{padding:26px 28px}} .og .lp-docs li{{font-size:18px;padding:13px 0}}
</style></head><body class="lp-page">
<div class="og"><div>
<div class="og__logo"><img src="{STATIC}/images/brand/logo/monituj-logo-white.svg" alt=""></div>
<p class="lp-mono lp-label"><b>●</b> {escape(label)}</p>
<h1>{escape(headline)} <em>{escape(accent)}</em></h1>
<p class="line">{escape(line)}</p>
</div>
<span class="og__site">MONITUJ.PL</span>
<div class="lp-card"><div class="lp-mono lp-card__top"><span>Prośba o dokumenty</span><span class="lp-live">Komplet</span></div>
<p class="lp-card__title">{escape(card_title)}</p>
<div class="lp-bar"><i></i><i></i><i></i><i></i></div>
<ul class="lp-docs">{rows}</ul></div>
</div></body></html>"""


async def render(pages):
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise SystemExit(
            "Needs Playwright: pip install playwright && playwright install chromium"
        ) from None
    OG_DIR.mkdir(parents=True, exist_ok=True)
    work = OG_DIR / ".og.html"
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        tab = await browser.new_page(viewport={"width": 1200, "height": 630})
        for name, *content in pages:
            work.write_text(page(*content), encoding="utf8")
            await tab.goto(work.as_uri(), wait_until="networkidle")
            await tab.evaluate("document.fonts.ready")
            await tab.screenshot(path=str(OG_DIR / f"{name}.png"))
        await browser.close()
    work.unlink()


def main():
    pages = PAGES + segment_pages()
    asyncio.run(render(pages))
    print(f"Saved {len(pages)} previews to {OG_DIR}")


if __name__ == "__main__":
    main()
