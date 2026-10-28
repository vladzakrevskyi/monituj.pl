"""Centrum pomocy: every article opens, links lead somewhere, and the search
finds the answer to questions typed the way people type them."""

import re

import pytest
from django.urls import reverse

from apps.help import articles
from apps.help.search import normalize, search
from apps.requests.services import RequestService
from tests.conftest import page_text


def test_links_between_articles_lead_somewhere():
    for article in articles.ARTICLES:
        assert article.category in articles.CATEGORY_BY_SLUG, article.slug
        for slug in article.related:
            assert slug in articles.BY_SLUG, (article.slug, slug)
        text = " ".join([article.summary, *article.steps, *article.body, *article.tips])
        for slug in re.findall(r"\[\[([a-z0-9-]+)", text):
            assert slug in articles.BY_SLUG, (article.slug, slug)


def test_panel_buttons_lead_somewhere():
    for article in articles.ARTICLES:
        if article.panel:
            reverse(article.panel[0])


def test_every_category_has_articles():
    for category in articles.CATEGORIES:
        assert articles.in_category(category.slug), category.slug


@pytest.mark.django_db
def test_every_page_opens(client):
    assert client.get(reverse("help:index")).status_code == 200
    for category in articles.CATEGORIES:
        url = reverse("help:category", args=[category.slug])
        assert client.get(url).status_code == 200, url
    for article in articles.ARTICLES:
        response = client.get(reverse("help:article", args=[article.slug]))
        assert response.status_code == 200, article.slug


@pytest.mark.django_db
def test_unknown_article_is_404(client):
    assert client.get("/pomoc/nie-ma-takiego/").status_code == 404
    assert client.get("/pomoc/temat/nie-ma-takiego/").status_code == 404


@pytest.mark.django_db
def test_an_article_shows_steps_tips_and_the_panel_button(client):
    page = page_text(client.get(reverse("help:article", args=["pierwsza-prosba"])))

    assert "Krok po kroku" in page and "Dobrze wiedzieć" in page
    assert "Otwórz w panelu: Nowa prośba" in page


@pytest.mark.django_db
def test_markup_is_rendered_and_text_escaped(client):
    html = client.get(reverse("help:article", args=["co-widzi-klient"])).content
    html = html.decode()

    assert f'href="{reverse("help:article", args=["jak-przeslac-dokumenty"])}"' in html
    assert "**" not in html and "[[" not in html


@pytest.mark.parametrize(
    "query, expected",
    [
        ("jak wysłać prośbę", "pierwsza-prosba"),
        ("jak wyslac prosbe", "pierwsza-prosba"),
        ("klient nie dostał maila", "klient-nie-dostal-maila"),
        ("zdjęcie telefonem", "z-telefonu"),
        ("import z excela", "import-klientow"),
        ("anulować subskrypcję", "zmien-anuluj-plan"),
        ("nie mam dokumentu", "nie-mam-dokumentu"),
        ("prośba co miesiąc", "prosba-co-miesiac"),
        ("jak przesłać dokumenty", "jak-przeslac-dokumenty"),
        ("2fa", "weryfikacja-dwuetapowa"),
        ("gdzie są moje pliki", "nie-widze-plikow"),
    ],
)
def test_search_finds_the_answer(query, expected):
    assert [a.slug for a in search(query)][0] == expected


def test_search_ignores_polish_letters_and_word_forms():
    assert normalize("Zażółć gęślą jaźń") == "zazolc gesla jazn"
    assert search("fakturę") and search("faktury")


def test_search_with_nothing_to_find():
    assert search("") == []
    assert search("jak to") == []
    assert search("xyzzy") == []


@pytest.mark.django_db
def test_live_search_answers_with_json(client):
    response = client.get(
        reverse("help:search"), {"q": "przypomnienia", "format": "json"}
    )

    results = response.json()["results"]
    assert results[0]["url"] == reverse(
        "help:article", args=["jak-dzialaja-przypomnienia"]
    )
    assert results[0]["category"] == "Przypomnienia"
    assert "**" not in results[0]["summary"]


@pytest.mark.django_db
def test_results_page_and_nothing_found(client):
    found = page_text(client.get(reverse("help:search"), {"q": "hasło"}))
    missing = page_text(client.get(reverse("help:search"), {"q": "xyzzy"}))

    assert "Jak zabezpieczyć prośbę hasłem" in found
    assert "Nic nie znaleźliśmy" in missing and "Napisz do nas" in missing


@pytest.mark.django_db
def test_results_page_is_not_indexed_but_articles_are(client):
    results = client.get(reverse("help:search"), {"q": "hasło"}).content.decode()
    article = client.get(reverse("help:article", args=["szablony"])).content.decode()

    assert 'content="noindex' in results
    assert 'content="index' in article


@pytest.mark.django_db
def test_sitemap_lists_the_help(client):
    sitemap = client.get(reverse("sitemap-xml")).content.decode()

    assert reverse("help:index") in sitemap
    assert reverse("help:article", args=["pierwsza-prosba"]) in sitemap
    assert reverse("help:category", args=["dla-klientow"]) in sitemap


@pytest.mark.django_db
def test_the_panel_menu_leads_to_help(client, user):
    client.force_login(user)

    html = client.get(reverse("requests:create")).content.decode()

    assert f'href="{reverse("help:index")}"' in html
    assert reverse("help:article", args=["pierwsza-prosba"]) in html


@pytest.mark.django_db
def test_the_clients_page_leads_to_their_help(client, user, client_record):
    request_obj = RequestService.create(
        owner=user,
        client_id=client_record.pk,
        name="Dokumenty",
        description="",
        deadline=None,
        item_names=["A"],
    )

    html = client.get(f"/d/{request_obj.public_token}/").content.decode()

    assert reverse("help:category", args=["dla-klientow"]) in html
