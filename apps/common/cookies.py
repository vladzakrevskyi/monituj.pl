"""Cookie categories and the tools that set them, described in one place.

Everything the visitor sees about cookies comes from here: the banner, the
"Ustawienia cookies" dialog, the cookie policy, the privacy policy - and the
Content-Security-Policy that lets those tools load at all.

To add a tool that runs through Google Tag Manager:
1. describe it in SERVICES below (skip if it's already there);
2. add its key to TRACKING_SERVICES in .env and restart;
3. in GTM, open the tag -> Consent settings -> require the consent types of
   its category (CATEGORIES[...]["consent"]), unless it's a Google tag, which
   reads them on its own.
Visitors are asked again whenever the list of active tools changes.
"""

import hashlib

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

# Google Consent Mode v2 types each category switches on. "necessary" is
# always granted; the rest stay denied until the visitor agrees.
CATEGORIES = {
    "necessary": {
        "name": "Niezbędne",
        "description": (
            "Logowanie, bezpieczeństwo formularzy, strefa czasowa i zapamiętanie "
            "Twojego wyboru w sprawie cookies. Bez nich Serwis nie działa, dlatego "
            "nie wymagają zgody."
        ),
        "required": True,
        "consent": ["functionality_storage", "security_storage"],
    },
    "preferences": {
        "name": "Funkcjonalne",
        "genitive": "funkcjonalnych",
        "description": (
            "Dodatkowe funkcje dostawców zewnętrznych, np. czat na stronie albo "
            "osadzone filmy."
        ),
        "consent": ["personalization_storage"],
    },
    "analytics": {
        "name": "Analityczne",
        "genitive": "analitycznych",
        "description": (
            "Statystyki odwiedzin: które strony są czytane, skąd przychodzą "
            "odwiedzający i co warto poprawić. Nie służą do reklam."
        ),
        "consent": ["analytics_storage"],
    },
    "marketing": {
        "name": "Marketingowe",
        "genitive": "marketingowych",
        "description": (
            "Pomiar skuteczności naszych reklam i pokazywanie reklam Monituj "
            "osobom, które odwiedziły Serwis (remarketing)."
        ),
        "consent": ["ad_storage", "ad_user_data", "ad_personalization"],
    },
}

# Monituj's own cookies, always set, no consent needed.
NECESSARY_COOKIES = [
    (
        "sessionid",
        "Utrzymanie sesji: logowanie do Konta oraz dostęp do prośby "
        "zabezpieczonej hasłem",
        "Do 2 tygodni lub do wylogowania",
    ),
    ("csrftoken", "Ochrona formularzy przed atakami typu CSRF", "Do 1 roku"),
    (
        "tz",
        "Strefa czasowa przeglądarki (np. „Europe/Warsaw”) – do wyświetlania dat "
        "w Twoim czasie i wysyłania przypomnień o właściwej godzinie. Nie zawiera "
        "danych, które pozwalają Cię zidentyfikować",
        "Do 1 roku",
    ),
    (
        "messages",
        "Wyświetlenie jednorazowego komunikatu po wykonaniu akcji (np. „Zmiany "
        "zostały zapisane”)",
        "Do wyświetlenia komunikatu",
    ),
]

CONSENT_STORAGE_KEY = "monituj-consent"
CONSENT_COOKIE = (
    f"{CONSENT_STORAGE_KEY} (pamięć przeglądarki)",
    "Zapamiętanie Twojego wyboru w sprawie cookies i losowego identyfikatora "
    "tej decyzji (służy do rejestru zgód, nie pozwala Cię zidentyfikować)",
    "12 miesięcy albo do zmiany wyboru",
)

GOOGLE = "Google Ireland Ltd."
GOOGLE_TRANSFER = "Google LLC (USA)"

# Tools that can be switched on with TRACKING_SERVICES. For each:
# - cookies: (name, purpose, lifetime); first_party=False marks cookies set
#   on the provider's own domain - we can't delete those, only stop the tool;
# - csp: sources the tool loads from, added to the Content-Security-Policy;
# - transfer: who outside the EEA may receive data (EU-US Data Privacy
#   Framework), shown in the privacy policy.
SERVICES = {
    "ga4": {
        "name": "Google Analytics 4",
        "provider": GOOGLE,
        "category": "analytics",
        "purpose": "Statystyki odwiedzin stron informacyjnych Serwisu",
        "data": (
            "identyfikator cookie, przybliżona lokalizacja, informacje o urządzeniu "
            "i odwiedzonych stronach"
        ),
        "retention": "dane w Google Analytics – 14 miesięcy",
        "transfer": GOOGLE_TRANSFER,
        "policy_url": "https://policies.google.com/privacy",
        "cookies": [
            ("_ga", "Rozróżnianie odwiedzających w statystykach", "Do 2 lat"),
            ("_ga_*", "Utrzymanie stanu sesji w statystykach", "Do 2 lat"),
        ],
        "csp": {
            "img-src": [
                "https://*.google-analytics.com",
                "https://*.googletagmanager.com",
            ],
            "connect-src": [
                "https://*.google-analytics.com",
                "https://*.analytics.google.com",
                "https://*.googletagmanager.com",
            ],
        },
    },
    "google_ads": {
        "name": "Google Ads",
        "provider": GOOGLE,
        "category": "marketing",
        "purpose": "Pomiar konwersji z reklam Google i remarketing",
        "data": "identyfikator cookie, kliknięcie reklamy, odwiedzone strony",
        "retention": "do 540 dni w Google Ads",
        "transfer": GOOGLE_TRANSFER,
        "policy_url": "https://policies.google.com/privacy",
        "cookies": [
            ("_gcl_au", "Przypisanie wizyty do kliknięcia reklamy", "Do 90 dni"),
            ("_gcl_aw", "Zapamiętanie kliknięcia reklamy Google", "Do 90 dni"),
            (
                "IDE",
                "Remarketing Google (domena doubleclick.net)",
                "Do 13 miesięcy",
                False,
            ),
        ],
        "csp": {
            "script-src": [
                "https://www.googleadservices.com",
                "https://googleads.g.doubleclick.net",
                "https://www.google.com",
            ],
            "img-src": [
                "https://googleads.g.doubleclick.net",
                "https://www.google.com",
                "https://www.google.pl",
            ],
            "connect-src": [
                "https://googleads.g.doubleclick.net",
                "https://www.google.com",
                "https://pagead2.googlesyndication.com",
            ],
            "frame-src": [
                "https://bid.g.doubleclick.net",
                "https://td.doubleclick.net",
            ],
        },
    },
    "meta_pixel": {
        "name": "Meta Pixel",
        "provider": "Meta Platforms Ireland Ltd.",
        "category": "marketing",
        "purpose": (
            "Pomiar skuteczności reklam na Facebooku i Instagramie oraz remarketing"
        ),
        "data": "identyfikator cookie, odwiedzone strony, informacje o urządzeniu",
        "retention": "zgodnie z zasadami Meta, zwykle do 2 lat",
        "transfer": "Meta Platforms, Inc. (USA)",
        "policy_url": "https://www.facebook.com/privacy/policy/",
        "cookies": [
            (
                "_fbp",
                "Rozróżnianie odwiedzających na potrzeby reklam Meta",
                "Do 90 dni",
            ),
            ("fr", "Reklamy Meta (domena facebook.com)", "Do 90 dni", False),
        ],
        "csp": {
            "script-src": ["https://connect.facebook.net"],
            "img-src": ["https://www.facebook.com"],
            "connect-src": ["https://www.facebook.com", "https://connect.facebook.net"],
        },
    },
    "clarity": {
        "name": "Microsoft Clarity",
        "provider": "Microsoft Ireland Operations Ltd.",
        "category": "analytics",
        "purpose": (
            "Mapy kliknięć i nagrania sesji – jak odwiedzający korzystają ze strony"
        ),
        "data": (
            "identyfikator cookie, ruchy myszy, kliknięcia i przewijanie, informacje "
            "o urządzeniu (bez treści wpisywanych w formularze)"
        ),
        "retention": "nagrania w Clarity – do 30 dni",
        "transfer": "Microsoft Corporation (USA)",
        "policy_url": "https://privacy.microsoft.com/pl-pl/privacystatement",
        "cookies": [
            ("_clck", "Rozróżnianie odwiedzających w Clarity", "Do 1 roku"),
            ("_clsk", "Łączenie odsłon w jedno nagranie sesji", "Do 1 dnia"),
            ("CLID", "Identyfikator Clarity (domena clarity.ms)", "Do 1 roku", False),
            ("MUID", "Identyfikator Microsoft (domena bing.com)", "Do 1 roku", False),
        ],
        "csp": {
            "script-src": ["https://www.clarity.ms", "https://*.clarity.ms"],
            "img-src": ["https://*.clarity.ms", "https://c.bing.com"],
            "connect-src": ["https://*.clarity.ms", "https://c.bing.com"],
        },
    },
    "linkedin": {
        "name": "LinkedIn Insight Tag",
        "provider": "LinkedIn Ireland Unlimited Company",
        "category": "marketing",
        "purpose": "Pomiar skuteczności reklam na LinkedIn i remarketing",
        "data": "identyfikator cookie, odwiedzone strony, informacje o urządzeniu",
        "retention": "zgodnie z zasadami LinkedIn, do 180 dni",
        "transfer": "LinkedIn Corporation (USA)",
        "policy_url": "https://www.linkedin.com/legal/privacy-policy",
        "cookies": [
            (
                "li_fat_id",
                "Przypisanie wizyty do kliknięcia reklamy LinkedIn",
                "Do 30 dni",
            ),
            (
                "bcookie",
                "Identyfikator przeglądarki (domena linkedin.com)",
                "Do 1 roku",
                False,
            ),
            ("lidc", "Wybór centrum danych (domena linkedin.com)", "Do 1 dnia", False),
            (
                "UserMatchHistory",
                "Dopasowanie reklam LinkedIn (domena linkedin.com)",
                "Do 30 dni",
                False,
            ),
        ],
        "csp": {
            "script-src": ["https://snap.licdn.com"],
            "img-src": ["https://px.ads.linkedin.com", "https://www.linkedin.com"],
            "connect-src": ["https://px.ads.linkedin.com"],
        },
    },
}

# Google Tag Manager itself sets no cookies; it only loads the tools above.
GTM_CSP = {"script-src": ["https://www.googletagmanager.com"]}


def _cookie(entry):
    name, purpose, lifetime, *rest = entry
    return {
        "name": name,
        "purpose": purpose,
        "lifetime": lifetime,
        "first_party": rest[0] if rest else True,
    }


def active_service_keys():
    from apps.common.analytics import gtm_id

    if not gtm_id():
        return []
    keys = list(getattr(settings, "TRACKING_SERVICES", []))
    unknown = [key for key in keys if key not in SERVICES]
    if unknown:
        raise ImproperlyConfigured(
            f"TRACKING_SERVICES: unknown {unknown}; known: {sorted(SERVICES)}"
        )
    return keys


def active_services():
    services = []
    for key in active_service_keys():
        service = dict(SERVICES[key], key=key)
        service["cookies"] = [_cookie(entry) for entry in service["cookies"]]
        service["category_name"] = CATEGORIES[service["category"]]["name"]
        service["category_genitive"] = CATEGORIES[service["category"]]["genitive"]
        services.append(service)
    return services


def csp_sources():
    """Extra Content-Security-Policy sources for GTM and the active tools."""
    keys = active_service_keys()
    if not keys:
        return {}
    extra = {}
    for sources in [GTM_CSP, *(SERVICES[key]["csp"] for key in keys)]:
        for directive, values in sources.items():
            bucket = extra.setdefault(directive, [])
            bucket.extend(value for value in values if value not in bucket)
    return extra


def join_pl(words):
    """ "a", "a i b", "a, b i c" """
    words = list(words)
    return " i ".join([", ".join(words[:-1]), words[-1]] if len(words) > 1 else words)


def version(keys):
    """Changes whenever the set of tools does, so visitors are asked again."""
    return hashlib.sha256(",".join(sorted(keys)).encode()).hexdigest()[:10]


def consent():
    """Everything the banner, the dialog and the policies need."""
    services = active_services()
    categories = []
    for key, category in CATEGORIES.items():
        members = [s for s in services if s["category"] == key]
        if category.get("required") or members:
            categories.append(dict(category, key=key, services=members))
    optional = [c for c in categories if not c.get("required")]
    return {
        "enabled": bool(services),
        "services": services,
        "categories": categories,
        "optional_categories": optional,
        # "analitycznych i marketingowych", as in "cookies ..."
        "optional_genitive": join_pl(c["genitive"] for c in optional),
        "service_names": ", ".join(s["name"] for s in services),
        "necessary_cookies": [_cookie(entry) for entry in NECESSARY_COOKIES],
        "consent_cookie": _cookie(CONSENT_COOKIE),
        "transfers": [s for s in services if s.get("transfer")],
        # For static/js/consent.js; category keys -> consent types and the
        # first-party cookies to delete when consent is withdrawn.
        "config": {
            "version": version(s["key"] for s in services),
            "storageKey": CONSENT_STORAGE_KEY,
            "granted": CATEGORIES["necessary"]["consent"],
            "categories": {
                c["key"]: {
                    "consent": c["consent"],
                    "cookies": sorted(
                        {
                            cookie["name"]
                            for s in c["services"]
                            for cookie in s["cookies"]
                            if cookie["first_party"]
                        }
                    ),
                }
                for c in optional
            },
        },
    }
