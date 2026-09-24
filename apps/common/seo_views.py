"""robots.txt, sitemap.xml, llms.txt, the web manifest and the root icon
addresses browsers and crawlers ask for."""

import json
from datetime import UTC, datetime
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from apps.common import seo
from apps.common.content import FAQ, SEGMENTS
from apps.common.middleware import PRIVATE_PREFIXES
from apps.common.site import absolute_url

# Private or pointless for search: the panel, token links, forms that only
# make sense from an email, the API. Those pages also send "noindex".
PRIVATE_PATHS = [
    *PRIVATE_PREFIXES,
    "/logowanie/",
    "/wyloguj/",
    "/wyslij-prosbe/sprawdz-skrzynke/",
    "/demo/start/",
    "/demo/zakoncz/",
]

TEMPLATES_DIR = Path(settings.BASE_DIR) / "templates"
CONTENT_FILE = Path(settings.BASE_DIR) / "apps" / "common" / "content.py"


def _modified(*paths):
    stamps = [p.stat().st_mtime for p in paths if p.exists()]
    moment = datetime.fromtimestamp(max(stamps), tz=UTC) if stamps else None
    return moment.date().isoformat() if moment else None


def sitemap_entries():
    entries = []
    for view_name, page in seo.PAGES.items():
        entries.append(
            {
                "loc": absolute_url(reverse(view_name)),
                "lastmod": _modified(TEMPLATES_DIR / page["template"], CONTENT_FILE),
                "priority": page["priority"],
            }
        )
    segment_modified = _modified(TEMPLATES_DIR / "pages/segment.html", CONTENT_FILE)
    for segment in SEGMENTS:
        entries.append(
            {
                "loc": absolute_url(reverse("pages:segment", args=[segment["slug"]])),
                "lastmod": segment_modified,
                "priority": "0.8",
            }
        )
    return entries


@require_GET
@cache_control(max_age=3600, public=True)
def robots_txt(request):
    lines = ["User-agent: *", "Allow: /"]
    lines += [f"Disallow: {path}" for path in PRIVATE_PATHS]
    lines += ["", f"Sitemap: {absolute_url('/sitemap.xml')}", ""]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


@require_GET
@cache_control(max_age=3600, public=True)
def sitemap_xml(request):
    body = render_to_string("seo/sitemap.xml", {"entries": sitemap_entries()})
    return HttpResponse(body, content_type="application/xml; charset=utf-8")


def _llms_context():
    pages = [
        {
            "title": page.get("label") or "Strona główna",
            "url": absolute_url(reverse(view_name)),
            "description": page["description"],
        }
        for view_name, page in seo.PAGES.items()
        if not view_name.startswith("legal:") and view_name != "accounts:register"
    ]
    segments = [
        {
            **segment,
            "url": absolute_url(reverse("pages:segment", args=[segment["slug"]])),
        }
        for segment in SEGMENTS
    ]
    legal = [
        {
            "title": seo.PAGES[name]["label"],
            "url": absolute_url(reverse(name)),
        }
        for name in ("legal:terms", "legal:privacy", "legal:dpa")
    ]
    return {
        "pages": pages,
        "segments": segments,
        "faq": FAQ,
        "legal": legal,
        "contact_email": settings.CONTACT_EMAIL,
        "site_url": absolute_url("/"),
        "register_url": absolute_url(reverse("accounts:register")),
        "guest_url": absolute_url(reverse("public:guest-request-create")),
    }


@require_GET
@cache_control(max_age=3600, public=True)
def llms_txt(request):
    body = render_to_string("seo/llms.txt", _llms_context())
    return HttpResponse(body, content_type="text/markdown; charset=utf-8")


@require_GET
@cache_control(max_age=3600, public=True)
def llms_full_txt(request):
    body = render_to_string("seo/llms-full.txt", _llms_context())
    return HttpResponse(body, content_type="text/markdown; charset=utf-8")


@require_GET
@cache_control(max_age=86400, public=True)
def web_manifest(request):
    manifest = {
        "name": "Monituj – zbieranie dokumentów od klientów",
        "short_name": "Monituj",
        "description": seo.DEFAULT_DESCRIPTION,
        "lang": "pl",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#f1f1f3",
        "theme_color": "#0b0b0c",
        "icons": [
            {
                "src": static("images/brand/icon-192.png"),
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": static("images/brand/icon-512.png"),
                "sizes": "512x512",
                "type": "image/png",
            },
            {
                "src": static("images/brand/icon-maskable-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
    }
    return HttpResponse(
        json.dumps(manifest, ensure_ascii=False),
        content_type="application/manifest+json; charset=utf-8",
    )


@require_GET
def favicon(request):
    # Temporary: the static file name carries a content hash in production,
    # so a cached permanent redirect would outlive the file.
    return redirect(static("images/brand/favicon.ico"))


@require_GET
def apple_touch_icon(request):
    return redirect(static("images/brand/apple-touch-icon.png"))
