"""The promo film: its own page /film/, the home page (hero button + its own
section) and "Jak to działa"."""

import re
import xml.etree.ElementTree as ET
from datetime import datetime

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
    assert film.iso_duration().startswith("PT4M")


@pytest.mark.django_db
def test_home_page_opens_the_film_in_a_dialog_from_the_hero(client):
    minutes, seconds = divmod(film.SECONDS, 60)
    page = client.get("/").content.decode()

    # Without JavaScript the button leads to the film's own page.
    assert (
        f'href="{reverse("pages:film")}" data-video-open aria-controls="film-dialog"'
        in page
    )
    assert f"Zobacz film · {minutes}:{seconds:02d}</a>" in page
    assert '<dialog class="video-dialog" id="film-dialog" data-modal-custom' in page
    assert page.count("data-promo-video") == 1  # only in the dialog
    assert "data-chapter " not in page
    assert 'preload="none"' in page
    assert "js/promo_video.js" in page


@pytest.mark.django_db
def test_chapter_seconds_are_not_localized(client):
    page = client.get(reverse("pages:how-it-works")).content.decode()

    values = re.findall(r'data-(?:wide|tall)="([^"]*)"', page)
    assert len(values) == 2 * len(film.CHAPTERS)
    assert all(re.fullmatch(r"\d+(\.\d+)?", value) for value in values)


def _videos(client, path):
    blocks = _jsonld(_head(client.get(path)))
    return [
        node
        for block in blocks
        for node in block["@graph"]
        if node["@type"] == "VideoObject"
    ]


@pytest.mark.django_db
def test_search_engines_see_the_film_on_its_own_page(client):
    videos = _videos(client, "/film/")

    assert len(videos) == 1
    assert videos[0]["duration"] == film.iso_duration()


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/", "/jak-to-dziala/"])
def test_other_pages_show_the_film_but_do_not_claim_it(client, path):
    page = client.get(path).content.decode()

    assert _videos(client, path) == []
    assert "data-promo-video" in page
    assert 'href="/film/"' in page


@pytest.mark.django_db
def test_film_addresses_stay_the_same_when_the_film_is_re_cut(client):
    video = _videos(client, "/film/")[0]

    assert video["contentUrl"] == "http://localhost:8000/static/" + film.WIDE
    assert video["thumbnailUrl"] == "http://localhost:8000/static/" + film.WIDE_POSTER
    assert f'src="/static/{film.WIDE}"' in client.get("/film/").content.decode()


def test_upload_date_is_a_full_date_with_a_time_zone():
    published = datetime.fromisoformat(film.PUBLISHED)

    assert published.utcoffset() is not None


@pytest.mark.django_db
def test_film_page_opens_on_the_film_and_describes_each_chapter(client):
    page = client.get("/film/").content.decode()

    assert page.count("data-deep-link") == 1
    assert page.index("data-promo-video") < page.index("Co zobaczysz")
    assert page.count("data-film-chapter") == len(film.CHAPTERS)
    assert f'href="?t={int(film.CHAPTERS[1][1])}"' in page
    assert "js/promo_video.js" in page


@pytest.mark.django_db
def test_clips_mark_every_chapter_up_to_the_end_of_the_film(client):
    clips = _videos(client, "/film/")[0]["hasPart"]

    assert [clip["name"] for clip in clips] == [c[0] for c in film.CHAPTERS]
    second = int(film.CHAPTERS[1][1])
    assert clips[1]["url"] == f"http://localhost:8000/film/?t={second}"
    assert clips[-1]["endOffset"] == film.SECONDS
    starts = [clip["startOffset"] for clip in clips]
    assert len(starts) == len(set(starts))
    assert all(clip["endOffset"] > clip["startOffset"] for clip in clips)


@pytest.mark.django_db
def test_sitemap_describes_the_film_on_its_page(client):
    root = ET.fromstring(client.get("/sitemap.xml").content)
    ns = {
        "s": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "v": "http://www.google.com/schemas/sitemap-video/1.1",
    }
    entries = root.findall("s:url[v:video]", ns)

    assert [entry.find("s:loc", ns).text for entry in entries] == [
        "http://localhost:8000/film/"
    ]
    video = entries[0].find("v:video", ns)
    assert video.find("v:content_loc", ns).text.endswith(film.WIDE)
    assert video.find("v:thumbnail_loc", ns).text.endswith(film.WIDE_POSTER)
    assert video.find("v:duration", ns).text == str(film.SECONDS)
    assert video.find("v:publication_date", ns).text == film.PUBLISHED
