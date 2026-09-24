import json
import re
import xml.etree.ElementTree as ET

import pytest
from django.urls import reverse

from apps.common.content import SEGMENTS
from apps.common.seo import PAGES
from apps.common.templatetags.seo_tags import ld_json

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def _head(response):
    html = response.content.decode()
    return html[: html.index("</head>")]


def _meta(head, attr, name):
    match = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)"', head)
    return match.group(1) if match else None


def _jsonld(head):
    return [
        json.loads(block)
        for block in re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', head, re.S
        )
    ]


def _types(blocks):
    return {node["@type"] for block in blocks for node in block["@graph"]}


TITLE_SHAPE = re.compile(r"^[^|]+ \| monituj\.pl$")


def test_titles_share_one_shape_and_descriptions_fit_search_results():
    for page in PAGES.values():
        assert TITLE_SHAPE.match(page["title"]), page["title"]
        assert len(page["title"]) <= 60, page["title"]
        assert 50 <= len(page["description"]) <= 160 or "legal" in page["template"]
    for segment in SEGMENTS:
        assert len(f"{segment['seo_name']} | monituj.pl") <= 60
        assert len(segment["seo_description"]) <= 160


def test_page_names_use_no_separators_of_their_own():
    """One style everywhere: "<page name> | monituj.pl", no colons or dashes
    inside the name."""
    names = [p["name"] for p in PAGES.values()] + [s["seo_name"] for s in SEGMENTS]
    for name in names:
        assert not set(name) & set(":–—-|"), name


def test_panel_page_names_use_no_separators_either():
    from pathlib import Path

    for template in Path("templates").rglob("*.html"):
        for name in re.findall(
            r"\{% block page_name %\}(.*?)\{% endblock %\}", template.read_text()
        ):
            assert not set(name) & set(":–—-|"), (template, name)


def test_every_indexed_page_has_a_unique_title():
    names = [p["name"] for p in PAGES.values()] + [s["seo_name"] for s in SEGMENTS]
    assert len(names) == len(set(names))


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path, name",
    [
        ("/", "Automatyczne zbieranie dokumentów od klientów"),
        ("/dla-kogo/kadry/", "Dokumenty do akt nowego pracownika"),
        ("/logowanie/", "Zaloguj się"),
    ],
)
def test_page_titles_follow_the_house_style(client, path, name):
    head = _head(client.get(path))

    assert f"<title>{name} | monituj.pl</title>" in head


@pytest.mark.django_db
@pytest.mark.parametrize("name", list(PAGES))
def test_public_pages_are_indexable_with_full_metadata(client, name):
    head = _head(client.get(reverse(name)))

    assert f"<title>{PAGES[name]['title']}</title>" in head.replace("\u00a0", " ")
    assert _meta(head, "name", "robots").startswith("index, follow")
    assert f'<link rel="canonical" href="http://localhost:8000{reverse(name)}">' in (
        head
    )
    assert _meta(head, "property", "og:title") == PAGES[name]["title"]
    assert _meta(head, "property", "og:image").endswith(".png")
    assert _meta(head, "name", "twitter:card") == "summary_large_image"
    assert _jsonld(head)


@pytest.mark.django_db
def test_landing_describes_the_organization_and_the_product(client):
    types = _types(_jsonld(_head(client.get("/"))))

    assert {"Organization", "WebSite", "SoftwareApplication", "FAQPage"} <= types


@pytest.mark.django_db
def test_faq_page_marks_up_every_question(client):
    from apps.common.content import FAQ

    blocks = _jsonld(_head(client.get(reverse("pages:faq"))))
    faq = next(n for b in blocks for n in b["@graph"] if n["@type"] == "FAQPage")

    assert len(faq["mainEntity"]) == len(FAQ)


@pytest.mark.django_db
@pytest.mark.parametrize("segment", SEGMENTS, ids=lambda s: s["slug"])
def test_industry_pages(client, segment):
    response = client.get(reverse("pages:segment", args=[segment["slug"]]))
    head = _head(response)
    text = response.content.decode().replace("\u00a0", " ")

    assert response.status_code == 200
    assert segment["h1"] in text
    assert _meta(head, "name", "robots").startswith("index")
    assert f"og/segment-{segment['slug']}.png" in _meta(head, "property", "og:image")
    assert {"BreadcrumbList", "FAQPage"} <= _types(_jsonld(head))


@pytest.mark.django_db
def test_unknown_industry_is_not_found(client):
    assert client.get("/dla-kogo/nie-istnieje/").status_code == 404


@pytest.mark.django_db
def test_guide_is_an_article(client):
    blocks = _jsonld(_head(client.get(reverse("pages:guide"))))

    assert "Article" in _types(blocks)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path", ["/logowanie/", "/wyslij-prosbe/sprawdz-skrzynke/", "/dostep/wyslij/"]
)
def test_private_pages_are_never_indexed(client, path):
    head = _head(client.get(path))

    assert _meta(head, "name", "robots") == "noindex, nofollow"
    assert 'rel="canonical"' not in head
    assert _jsonld(head) == []


@pytest.mark.django_db
def test_private_pages_do_not_leak_their_title_into_link_previews(client, user):
    client.force_login(user)

    head = _head(client.get(reverse("clients:list")))

    # The page's own name ("Klienci") stays in <title> only, never in previews.
    assert _meta(head, "property", "og:title") == (
        "Zbieranie dokumentów od klientów | monituj.pl"
    )
    assert "<title>Klienci | monituj.pl</title>" in head


@pytest.mark.django_db
def test_panel_and_token_links_send_a_noindex_header(client):
    for path in ("/panel/", "/d/any-token/", "/moje-prosby/any/", "/api/clients/"):
        assert client.get(path)["X-Robots-Tag"] == "noindex, nofollow", path
    assert "X-Robots-Tag" not in client.get("/")


@pytest.mark.django_db
def test_robots_txt(client):
    body = client.get("/robots.txt").content.decode()

    assert "User-agent: *" in body
    assert "Disallow: /panel/" in body
    assert "Disallow: /d/" in body
    assert "Disallow: /dla-kogo/" not in body
    assert "Sitemap: http://localhost:8000/sitemap.xml" in body


@pytest.mark.django_db
def test_sitemap_lists_every_public_page_and_nothing_private(client):
    response = client.get("/sitemap.xml")
    root = ET.fromstring(response.content)
    urls = {loc.text for loc in root.iter(f"{SITEMAP_NS}loc")}

    assert response["Content-Type"].startswith("application/xml")
    for name in PAGES:
        assert f"http://localhost:8000{reverse(name)}" in urls
    for segment in SEGMENTS:
        assert f"http://localhost:8000/dla-kogo/{segment['slug']}/" in urls
    assert not any("/panel/" in url or "/logowanie/" in url for url in urls)


@pytest.mark.django_db
def test_llms_files_explain_the_product_to_ai_assistants(client):
    short = client.get("/llms.txt").content.decode()
    full = client.get("/llms-full.txt").content.decode()

    assert short.startswith("# Monituj")
    assert "zbierania dokumentów od klientów" in short
    assert "http://localhost:8000/llms-full.txt" in short
    assert "## Najczęstsze pytania" in full
    assert "Biura rachunkowe" in full


@pytest.mark.django_db
def test_web_manifest_and_icons(client):
    manifest = json.loads(client.get("/site.webmanifest").content)

    assert manifest["short_name"] == "Monituj"
    assert {icon["sizes"] for icon in manifest["icons"]} == {"192x192", "512x512"}
    assert client.get("/favicon.ico").url.endswith("images/brand/favicon.ico")
    assert client.get("/apple-touch-icon.png").status_code == 302


def test_structured_data_cannot_break_out_of_its_script_tag():
    rendered = ld_json({"name": "</script><script>alert(1)</script>"})

    assert rendered.count("</script>") == 1
    assert "\\u003C/script\\u003E" in rendered


@pytest.mark.django_db
def test_site_verification_tags_appear_when_configured(client, settings):
    settings.GOOGLE_SITE_VERIFICATION = "google-token-123"

    head = _head(client.get("/"))

    assert _meta(head, "name", "google-site-verification") == "google-token-123"
