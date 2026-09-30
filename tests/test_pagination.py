"""The pager every list shares: first/previous/next/last, page numbers with
the middle elided, filters kept in every link."""

import re

import pytest
from django.core.paginator import Paginator
from django.template import Context, Template
from django.test import RequestFactory
from django.urls import reverse

from apps.clients.models import Client


def _render(page, total_pages, query=""):
    request = RequestFactory().get(f"/lista/?{query}")
    page_obj = Paginator(range(total_pages * 10), 10).get_page(page)
    return Template("{% load pagination %}{% pagination page_obj %}").render(
        Context({"request": request, "page_obj": page_obj})
    )


def _numbers(html):
    return re.findall(r'class="pagination__page[^"]*"[^>]*>(\d+)<', html)


def test_long_list_shows_the_ends_and_the_pages_around_the_current():
    html = _render(10, 30, "status=brak&q=faktura")

    assert _numbers(html) == ["1", "9", "10", "11", "30"]
    assert html.count("&hellip;") == 2
    assert 'aria-current="page">10<' in html
    # First, previous, next and last keep the filters.
    assert (
        'href="?status=brak&amp;q=faktura&amp;page=1" title="Pierwsza strona"' in html
    )
    assert 'href="?status=brak&amp;q=faktura&amp;page=9"' in html
    assert 'href="?status=brak&amp;q=faktura&amp;page=11"' in html
    assert (
        'href="?status=brak&amp;q=faktura&amp;page=30" title="Ostatnia strona' in html
    )


@pytest.mark.parametrize(
    "current, expected",
    [
        (1, "1 2 3 4 5 … 8"),
        (4, "1 2 3 4 5 … 8"),
        (5, "1 … 4 5 6 7 8"),
        (8, "1 … 4 5 6 7 8"),
    ],
)
def test_never_more_than_seven_numbers(current, expected):
    assert _shown(_render(current, 8)) == expected


def test_a_short_list_shows_every_page():
    assert _shown(_render(4, 7)) == "1 2 3 4 5 6 7"


def _shown(html):
    return " ".join(
        "…" if part == "&hellip;" else part
        for part in re.findall(
            r'class="pagination__(?:page|gap)[^"]*"[^>]*>(\d+|&hellip;)<', html
        )
    )


def test_first_page_has_no_way_back():
    html = _render(1, 3)

    assert _numbers(html) == ["1", "2", "3"]
    assert "Pierwsza strona" not in html and "Poprzednia strona" not in html
    assert 'href="?page=3" title="Ostatnia strona' in html
    assert "&hellip;" not in html


def test_one_page_needs_no_pager():
    assert "pagination" not in _render(1, 1)


@pytest.mark.django_db
def test_client_list_pages_keep_the_search(client, user):
    Client.objects.bulk_create(
        Client(owner=user, name=f"Firma {n:02}", email=f"f{n}@example.com")
        for n in range(45)
    )
    client.force_login(user)

    html = client.get(
        reverse("clients:list"), {"q": "Firma", "page": 2}
    ).content.decode()

    assert 'aria-current="page">2<' in html
    assert 'href="?q=Firma&amp;page=3"' in html
    assert 'href="?q=Firma&amp;page=1" title="Pierwsza strona"' in html
