import re

import pytest
from django.core import mail
from django.urls import reverse

from apps.common.link_titles import add_link_titles
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService

LINK = re.compile(r"<a\b[^>]*>", re.I)


def _untitled(html):
    return [tag for tag in LINK.findall(html) if "title=" not in tag]


def test_link_text_becomes_the_title():
    assert add_link_titles('<a href="/x">Cennik</a>') == (
        '<a title="Cennik" href="/x">Cennik</a>'
    )


def test_markup_inside_the_link_is_ignored_and_arrows_dropped():
    html = '<a href="/x"><svg><path/></svg> <strong>Dalej</strong> &rarr;</a>'

    assert 'title="Dalej"' in add_link_titles(html)


def test_icon_links_fall_back_to_their_label():
    html = '<a href="/x" aria-label="Zamknij menu"><svg></svg></a>'

    assert 'title="Zamknij menu"' in add_link_titles(html)


def test_titles_written_by_hand_are_kept():
    html = '<a href="/" title="Monituj – strona główna">M Monituj</a>'

    assert add_link_titles(html) == html


def test_link_text_cannot_break_out_of_the_attribute():
    html = '<a href="/x">&quot; onmouseover=&quot;alert(1)</a>'

    result = add_link_titles(html)

    assert 'onmouseover="' not in result
    assert "&quot; onmouseover=&quot;alert(1)" in result


def test_scripts_are_left_alone():
    html = "<script>const a = '<a href=\"/x\">x</a>';</script>"

    assert add_link_titles(html) == html


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/jak-to-dziala/",
        "/funkcje/",
        "/dla-kogo/",
        "/dla-kogo/biura-rachunkowe/",
        "/poradnik/jak-zbierac-dokumenty-od-klientow/",
        "/faq/",
        "/cennik/",
        "/kontakt/",
        "/wyslij-prosbe/",
        "/logowanie/",
        "/regulamin/",
    ],
)
def test_every_link_on_public_pages_has_a_title(client, path):
    assert _untitled(client.get(path).content.decode()) == []


@pytest.mark.django_db
def test_every_link_in_the_panel_has_a_title(client, user, request_record):
    client.force_login(user)

    for name, args in [
        ("accounts:panel", []),
        ("requests:list", []),
        ("requests:detail", [request_record.pk]),
        ("clients:list", []),
        ("accounts:settings", []),
    ]:
        html = client.get(reverse(name, args=args)).content.decode()
        assert _untitled(html) == [], name


@pytest.mark.django_db
def test_every_link_in_emails_has_a_title(request_record, request_item):
    EmailService.send(
        EmailTemplate.INVITATION,
        to_email=request_record.client.email,
        request=request_record,
    )

    html = mail.outbox[0].alternatives[0][0]
    assert LINK.findall(html)
    assert _untitled(html) == []
