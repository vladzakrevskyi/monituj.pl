"""The promo film on the home page (hero button + its own section) and on
"Jak to działa"."""

import re

import pytest
from django.contrib.staticfiles import finders
from django.urls import reverse

from apps.common import promo_video as film
from tests.test_seo import _head, _jsonld


def test_the_files_are_there():
    for path in (film.WIDE, film.TALL, film.WIDE_POSTER, film.TALL_POSTER, film.THUMB):
        assert finders.find(path), path


def test_chapters_run_in_order_within_the_film():
    for cut in (1, 2):
        starts = [chapter[cut] for chapter in film.CHAPTERS]
        assert starts == sorted(starts)
        assert 0 <= starts[0] and starts[-1] < film.SECONDS
    assert film.iso_duration().startswith("PT2M")


@pytest.mark.django_db
def test_home_page_has_the_film_the_hero_card_and_the_dialog(client):
    minutes, seconds = divmod(film.SECONDS, 60)
    page = client.get("/").content.decode()

    assert 'id="film"' in page
    assert (
        'class="film-card" href="#film" data-video-open aria-controls="film-dialog"'
        in page
    )
    assert "video/monituj-promo-thumb" in page
    assert f">{minutes}:{seconds:02d}</span>" in page
    assert '<dialog class="video-dialog" id="film-dialog" data-modal-custom' in page
    assert page.count("data-promo-video") == 2  # the section and the dialog
    assert page.count("data-chapter ") == len(film.CHAPTERS)  # chapters once
    assert 'preload="none"' in page
    assert "js/promo_video.js" in page


@pytest.mark.django_db
def test_chapter_seconds_are_not_localized(client):
    page = client.get(reverse("pages:how-it-works")).content.decode()

    values = re.findall(r'data-(?:wide|tall)="([^"]*)"', page)
    assert len(values) == 2 * len(film.CHAPTERS)
    assert all(re.fullmatch(r"\d+(\.\d+)?", value) for value in values)


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/", "/jak-to-dziala/"])
def test_search_engines_see_the_film(client, path):
    blocks = _jsonld(_head(client.get(path)))
    videos = [
        node
        for block in blocks
        for node in block["@graph"]
        if node["@type"] == "VideoObject"
    ]

    assert len(videos) == 1
    assert videos[0]["contentUrl"].endswith(".mp4")
    assert videos[0]["duration"] == film.iso_duration()
