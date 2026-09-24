"""Everything search engines and link previews see.

The one thing Monituj is about, and what every title and description leads
with: nobody should have to chase clients for documents. Main phrase:
"zbieranie dokumentów od klientów", with "przypomnienia o dokumentach" and
"brakujące dokumenty" around it.

Only pages listed in PAGES are indexed; everything else (panel, forms,
private links) gets "noindex" by default, so a new page is private until it
is added here on purpose."""

from django.conf import settings
from django.templatetags.static import static

from apps.common.site import absolute_url

SITE_NAME = "Monituj"
DEFAULT_DESCRIPTION = (
    "Przestań gonić klientów o dokumenty. Monituj wysyła listę potrzebnych "
    "dokumentów, sam przypomina o brakach i pilnuje terminów."
)
DEFAULT_OG_IMAGE = "images/og/default.png"
GUIDE_PUBLISHED = "2026-09-24"
GUIDE_MODIFIED = "2026-09-24"
OG_IMAGE_SIZE = (1200, 630)

# Every page title has the same shape: "<page name> | monituj.pl" - short
# enough to show in full in search results (about 60 characters), with the
# page's own keywords first. The slogan lives in descriptions and headings.
TITLE_SUFFIX = " | monituj.pl"
DEFAULT_PAGE_NAME = "Zbieranie dokumentów od klientów"


def page_title(name):
    return f"{name}{TITLE_SUFFIX}"


# url name -> page name, description (≤ 155), OG image, sitemap priority and
# breadcrumb label. Page names lead with what people search for.
PAGES = {
    "landing": {
        "name": "Automatyczne zbieranie dokumentów od klientów",
        "description": (
            "Przestań gonić klientów o dokumenty. Monituj wysyła listę, sam "
            "przypomina o brakach i pilnuje terminów. Klient przesyła pliki bez "
            "konta. Za darmo."
        ),
        "og_image": "images/og/landing.png",
        "priority": "1.0",
        "template": "pages/landing.html",
    },
    "pages:how-it-works": {
        "name": "Jak działa zbieranie dokumentów od klientów",
        "description": (
            "Tworzysz prośbę z listą dokumentów, klient dostaje link, a Monituj "
            "przypomina o brakach aż do kompletu. Zobacz cały proces krok po kroku."
        ),
        "og_image": "images/og/jak-to-dziala.png",
        "priority": "0.9",
        "label": "Jak to działa",
        "template": "pages/how_it_works.html",
    },
    "pages:features": {
        "name": "Przypomnienia i statusy dokumentów klientów",
        "description": (
            "Automatyczne przypomnienia o dokumentach, lista braków, akceptacja i "
            "odrzucanie plików, dostęp dla klienta bez konta i usuwanie plików "
            "zgodnie z RODO."
        ),
        "og_image": "images/og/funkcje.png",
        "priority": "0.8",
        "label": "Funkcje",
        "template": "pages/features.html",
    },
    "pages:for-whom": {
        "name": "Dla biur rachunkowych, kadr i kancelarii",
        "description": (
            "Monituj dla biur rachunkowych, działów kadr, kancelarii, pośredników "
            "kredytowych i firm B2B – wszędzie tam, gdzie praca czeka na "
            "dokumenty od klientów."
        ),
        "og_image": "images/og/dla-kogo.png",
        "priority": "0.8",
        "label": "Dla kogo",
        "template": "pages/for_whom.html",
    },
    "pages:guide": {
        "name": "Jak zbierać dokumenty od klientów bez gonienia",
        "description": (
            "Poradnik: jak ustalić listę dokumentów, termin i rytm przypomnień, "
            "żeby klienci przysyłali dokumenty na czas. Z gotowymi listami "
            "dokumentów dla branż."
        ),
        "og_image": "images/og/poradnik.png",
        "priority": "0.8",
        "label": "Jak zbierać dokumenty od klientów",
        "template": "pages/guide.html",
        "og_type": "article",
    },
    "pages:security": {
        "name": "Bezpieczne przesyłanie dokumentów i RODO",
        "description": (
            "Unikalne linki, opcjonalne hasła, prywatny magazyn plików, "
            "sprawdzanie typu pliku i automatyczne usuwanie po ustalonym czasie. "
            "Umowa powierzenia w cenie."
        ),
        "og_image": "images/og/bezpieczenstwo.png",
        "priority": "0.7",
        "label": "Bezpieczeństwo",
        "template": "pages/security.html",
    },
    "pages:pricing": {
        "name": "Cennik i bezpłatny dostęp do Monituj",
        "description": (
            "Monituj jest obecnie bezpłatny: prośby o dokumenty, automatyczne "
            "przypomnienia i panel z brakami. Możesz też wysłać prośbę bez "
            "zakładania konta."
        ),
        "og_image": "images/og/cennik.png",
        "priority": "0.7",
        "label": "Cennik",
        "template": "pages/pricing.html",
    },
    "pages:faq": {
        "name": "Pytania o zbieranie dokumentów od klientów",
        "description": (
            "Jak działają przypomnienia o dokumentach, czy klient musi zakładać "
            "konto, jak długo przechowujemy pliki i ile to kosztuje – odpowiedzi "
            "w jednym miejscu."
        ),
        "og_image": "images/og/faq.png",
        "priority": "0.7",
        "label": "Najczęstsze pytania",
        "template": "pages/faq.html",
    },
    "pages:demo": {
        "name": "Demo Monituj bez rejestracji",
        "description": (
            "Własne konto demonstracyjne z przykładowymi klientami i prośbami o "
            "dokumenty – gotowe w jedno kliknięcie, bez podawania adresu email."
        ),
        "og_image": "images/og/demo.png",
        "priority": "0.7",
        "label": "Demo",
        "template": "pages/demo.html",
    },
    "public:guest-request-create": {
        "name": "Wyślij prośbę o dokumenty bez konta",
        "description": (
            "Poproś klienta o dokumenty w 2 minuty: lista, termin i automatyczne "
            "przypomnienia. Bez rejestracji – potwierdzasz mailem i śledzisz "
            "status w panelu."
        ),
        "og_image": "images/og/wyslij-prosbe.png",
        "priority": "0.8",
        "label": "Wyślij prośbę bez konta",
        "template": "public/guest_request_form.html",
    },
    "pages:contact": {
        "name": "Kontakt",
        "description": (
            "Napisz do zespołu Monituj: pytania o zbieranie dokumentów od "
            "klientów, pomoc w koncie, sprawy RODO i zgłoszenia nadużyć."
        ),
        "priority": "0.5",
        "label": "Kontakt",
        "template": "pages/contact.html",
    },
    "accounts:register": {
        "name": "Załóż darmowe konto",
        "description": (
            "Załóż bezpłatne konto Monituj i wyślij pierwszą prośbę o dokumenty "
            "w 5 minut. Bez karty kredytowej, klienci nie zakładają kont."
        ),
        "priority": "0.6",
        "label": "Rejestracja",
        "template": "accounts/register.html",
    },
    "legal:terms": {
        "name": "Regulamin",
        "description": "Regulamin świadczenia usług drogą elektroniczną w Monituj.",
        "priority": "0.3",
        "label": "Regulamin",
        "template": "legal/terms.html",
    },
    "legal:privacy": {
        "name": "Polityka prywatności",
        "description": (
            "Jak Monituj przetwarza dane osobowe Użytkowników i Odbiorców, jak "
            "długo je przechowuje i jakie prawa Ci przysługują."
        ),
        "priority": "0.3",
        "label": "Polityka prywatności",
        "template": "legal/privacy.html",
    },
    "legal:cookies": {
        "name": "Polityka cookies",
        "description": (
            "Jakich plików cookies używa Monituj i do czego ich potrzebujemy."
        ),
        "priority": "0.2",
        "label": "Polityka cookies",
        "template": "legal/cookies.html",
    },
    "legal:dpa": {
        "name": "Umowa powierzenia",
        "description": (
            "Umowa powierzenia przetwarzania danych osobowych (art. 28 RODO) "
            "zawierana z Użytkownikami Monituj."
        ),
        "priority": "0.3",
        "label": "Umowa powierzenia",
        "template": "legal/dpa.html",
    },
}


for _page in PAGES.values():
    _page["title"] = page_title(_page["name"])
    _page.setdefault("label", _page["name"])


def build(request, name, description, og_image=None, indexable=True, **extra):
    """The `seo` context every page renders its <head> from."""
    canonical = absolute_url(request.path)
    image = og_image or DEFAULT_OG_IMAGE
    title = page_title(name)
    return {
        "page_name": name,
        "title": title,
        "description": description,
        "indexable": indexable,
        "robots": "index, follow, max-image-preview:large"
        if indexable
        else "noindex, nofollow",
        "canonical": canonical,
        "og_type": extra.get("og_type", "website"),
        "og_image": absolute_url(static(image)),
        "og_image_alt": extra.get("og_image_alt", title),
        "jsonld": extra.get("jsonld", []),
    }


def for_request(request):
    match = getattr(request, "resolver_match", None)
    page = PAGES.get(match.view_name) if match else None
    if page is None:
        return build(request, DEFAULT_PAGE_NAME, DEFAULT_DESCRIPTION, indexable=False)
    return build(
        request,
        page["name"],
        page["description"],
        og_image=page.get("og_image"),
        og_type=page.get("og_type", "website"),
        jsonld=_page_jsonld(match.view_name, page, request),
    )


# --- schema.org -----------------------------------------------------------


def organization():
    return {
        "@type": "Organization",
        "@id": absolute_url("/#organization"),
        "name": SITE_NAME,
        "url": absolute_url("/"),
        "logo": absolute_url(static("images/brand/icon-512.png")),
        "email": settings.CONTACT_EMAIL,
        "contactPoint": {
            "@type": "ContactPoint",
            "contactType": "customer support",
            "email": settings.CONTACT_EMAIL,
            "availableLanguage": ["pl"],
        },
    }


def website():
    return {
        "@type": "WebSite",
        "@id": absolute_url("/#website"),
        "name": SITE_NAME,
        "url": absolute_url("/"),
        "inLanguage": "pl-PL",
        "publisher": {"@id": absolute_url("/#organization")},
    }


def software_application():
    return {
        "@type": "SoftwareApplication",
        "name": SITE_NAME,
        "url": absolute_url("/"),
        "applicationCategory": "BusinessApplication",
        "operatingSystem": "Web",
        "inLanguage": "pl-PL",
        "description": PAGES["landing"]["description"],
        "featureList": [
            "Prośby o dokumenty z listą i terminem",
            "Automatyczne przypomnienia o brakujących dokumentach",
            "Przesyłanie plików przez klienta bez zakładania konta",
            "Akceptacja i odrzucanie dokumentów z podaniem powodu",
            "Automatyczne usuwanie plików po ustalonym czasie (RODO)",
        ],
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "PLN"},
        "publisher": {"@id": absolute_url("/#organization")},
    }


def faq_page(items):
    return {
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["q"],
                "acceptedAnswer": {"@type": "Answer", "text": item["a"]},
            }
            for item in items
        ],
    }


def breadcrumbs(trail):
    """trail: [(label, path), ...] after the home page."""
    items = [("Monituj", "/"), *trail]
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "name": label,
                "item": absolute_url(path),
            }
            for position, (label, path) in enumerate(items, start=1)
        ],
    }


def article(page, request):
    return {
        "@type": "Article",
        "headline": page["name"],
        "description": page["description"],
        "inLanguage": "pl-PL",
        "mainEntityOfPage": absolute_url(request.path),
        "image": absolute_url(static(page["og_image"])),
        "datePublished": GUIDE_PUBLISHED,
        "dateModified": GUIDE_MODIFIED,
        "author": {"@id": absolute_url("/#organization")},
        "publisher": {"@id": absolute_url("/#organization")},
    }


def segment_seo(request, segment):
    return build(
        request,
        segment["seo_name"],
        segment["seo_description"],
        og_image=f"images/og/segment-{segment['slug']}.png",
        jsonld=[
            graph(
                breadcrumbs(
                    [
                        (PAGES["pages:for-whom"]["label"], "/dla-kogo/"),
                        (segment["title"], request.path),
                    ]
                ),
                faq_page(segment["faq"]),
            )
        ],
    )


def graph(*nodes):
    return {"@context": "https://schema.org", "@graph": list(nodes)}


def _page_jsonld(view_name, page, request):
    from apps.common.content import FAQ

    if view_name == "landing":
        return [
            graph(
                organization(),
                website(),
                software_application(),
                faq_page([item for item in FAQ if item["home"]]),
            )
        ]
    nodes = [breadcrumbs([(page["label"], request.path)])]
    if view_name == "pages:guide":
        nodes.append(article(page, request))
    if view_name == "pages:faq":
        nodes.append(faq_page(FAQ))
    if view_name == "pages:pricing":
        nodes.append(software_application())
    return [graph(*nodes)]
