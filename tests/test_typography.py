import pytest
from django.core import mail
from django.urls import reverse

from apps.clients.models import Client
from apps.common.typography import NBSP, fix_orphans, fix_orphans_text
from apps.notifications.services import EmailService


def test_short_words_are_glued_to_the_next_word():
    assert fix_orphans_text("Pliki w chmurze i na dysku") == (
        f"Pliki w{NBSP}chmurze i{NBSP}na{NBSP}dysku"
    )


def test_chains_of_short_words_are_glued_fully():
    assert fix_orphans_text("a w domu") == f"a{NBSP}w{NBSP}domu"


def test_numbers_and_dashes_do_not_hang():
    assert fix_orphans_text("za 5 minut – gotowe") == (
        f"za{NBSP}5{NBSP}minut{NBSP}– gotowe"
    )


def test_longer_words_are_left_alone():
    assert fix_orphans_text("Monituj pilnuje terminów") == "Monituj pilnuje terminów"


def test_only_text_between_tags_changes():
    html = (
        '<input value="a b" placeholder="w domu"><script>let a = w + z;</script>'
        "<textarea>a b</textarea><p>Zacznij w <strong>kilka</strong> minut</p>"
    )

    result = fix_orphans(html)

    assert '<input value="a b" placeholder="w domu">' in result
    assert "<script>let a = w + z;</script>" in result
    assert "<textarea>a b</textarea>" in result
    assert f"Zacznij w{NBSP}<strong>kilka</strong>" in result


@pytest.mark.django_db
def test_pages_are_served_with_glued_short_words(client):
    content = client.get(reverse("pages:faq")).content.decode()

    assert f"w{NBSP}" in content


@pytest.mark.django_db
def test_json_responses_are_untouched(client, user):
    Client.objects.create(owner=user, name="Biuro w domu", email="a@example.com")
    client.force_login(user)

    response = client.get(reverse("clients_api:collection"))

    assert "Biuro w domu" in response.content.decode("unicode_escape")


@pytest.mark.django_db
def test_html_emails_get_the_same_typography():
    EmailService.send(
        "haslo_zmienione", to_email="ktos@example.com", context={}, log=False
    )

    html = mail.outbox[0].alternatives[0][0]
    assert f"w{NBSP}Monituj" in html
