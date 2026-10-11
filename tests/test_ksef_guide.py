"""The "Dokumenty spoza KSeF" guide and the places that lead to it."""

import pytest
from django.urls import reverse

from tests.test_seo import _head, _jsonld, _types

GUIDE = "/poradnik/dokumenty-spoza-ksef/"


@pytest.mark.django_db
def test_guide_is_an_indexed_article_with_its_own_dates(client):
    response = client.get(GUIDE)

    assert response.status_code == 200
    blocks = _jsonld(_head(response))
    assert {"BreadcrumbList", "Article"} <= _types(blocks)
    article = next(
        node
        for block in blocks
        for node in block["@graph"]
        if node["@type"] == "Article"
    )
    assert article["datePublished"] == "2026-10-11"
    page = response.content.decode()
    # It sends readers to the two ready lists it talks about.
    assert reverse("pages:template", args=["dokumenty-ksiegowe-za-miesiac"]) in page
    assert reverse("pages:template", args=["nowy-klient-biura-rachunkowego"]) in page


@pytest.mark.django_db
def test_guide_is_in_the_sitemap_and_linked_from_the_site(client):
    assert GUIDE in client.get("/sitemap.xml").content.decode()
    for path in ("/", "/dla-kogo/biura-rachunkowe/"):
        assert GUIDE in client.get(path).content.decode(), path
    # Only the accounting segment points at it.
    assert (
        GUIDE not in client.get("/dla-kogo/kadry/").content.decode().split("<footer")[0]
    )


@pytest.mark.django_db
def test_site_explains_items_without_a_file(client):
    assert "bez pliku" in client.get(reverse("pages:features")).content.decode()
    assert "Co z fakturami, które są w" in client.get(
        reverse("pages:faq")
    ).content.decode().replace(" ", " ")
