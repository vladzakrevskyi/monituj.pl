import time

import pytest
from django.core import mail, signing
from django.urls import reverse

from apps.contact.forms import EXPIRED_MESSAGE, MAX_AGE, TOKEN_SALT
from apps.contact.services import LIMIT_PER_HOUR
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService
from tests.conftest import page_text

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def _token(seconds_ago=30):
    """What the page handed out that long ago."""
    return signing.dumps(int(time.time()) - seconds_ago, salt=TOKEN_SALT)


def _message(seconds_ago=30, **overrides):
    """As a person sends it: the page open for a while, its script ran."""
    token = _token(seconds_ago)
    data = {
        "issued": token,
        "human": token[::-1],
        "name": "Jan Kowalski",
        "email": "jan@example.com",
        "company": "Biuro Kowalski",
        "topic": "wspolpraca",
        "message": "Dzień dobry,\nchcemy wdrożyć Monituj w biurze.",
        "website": "",
        "consent": "on",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_contact_page_shows_the_form_and_address(client):
    content = page_text(client.get(reverse("pages:contact")))

    assert 'name="message"' in content
    assert "mailto:kontakt@monituj.pl" in content


@pytest.mark.django_db
def test_footer_shows_contact_address_everywhere(client):
    content = client.get(reverse("pages:faq")).content.decode()

    assert 'class="site-footer__mail" href="mailto:kontakt@monituj.pl"' in content


@pytest.mark.django_db
def test_message_goes_to_the_team_with_reply_to_the_sender(client, settings):
    response = client.post(reverse("pages:contact"), _message(), **AJAX)

    assert response.status_code == 200
    assert response.json()["data"]["title"] == "Dziękujemy za wiadomość"
    team = next(m for m in mail.outbox if m.to == ["kontakt@monituj.pl"])
    assert team.from_email == settings.DEFAULT_FROM_EMAIL
    assert "no-reply@monituj.pl" in team.from_email
    assert team.reply_to == ["jan@example.com"]
    assert "Współpraca" in team.subject
    assert "chcemy wdrożyć Monituj" in team.body
    assert "Biuro Kowalski" in team.alternatives[0][0]


@pytest.mark.django_db
def test_sender_gets_a_confirmation_with_reply_to_the_team(client):
    client.post(reverse("pages:contact"), _message(), **AJAX)

    confirmation = next(m for m in mail.outbox if m.to == ["jan@example.com"])
    assert "no-reply@monituj.pl" in confirmation.from_email
    assert confirmation.reply_to == ["kontakt@monituj.pl"]
    # The sender's text is not echoed back to a possibly foreign address.
    assert "chcemy wdrożyć Monituj" not in confirmation.body
    assert len(mail.outbox) == 2


@pytest.mark.django_db
def test_invalid_fields_are_reported_under_the_inputs(client):
    response = client.post(
        reverse("pages:contact"),
        _message(email="zly-adres", message="krótko"),
        **AJAX,
    )

    assert response.status_code == 400
    fields = response.json()["error"]["fields"]
    assert set(fields) == {"email", "message"}
    assert mail.outbox == []


@pytest.mark.django_db
def test_message_is_not_sent_without_consent(client):
    data = _message()
    del data["consent"]

    response = client.post(reverse("pages:contact"), data, **AJAX)

    assert response.status_code == 400
    assert list(response.json()["error"]["fields"]) == ["consent"]
    assert mail.outbox == []


@pytest.mark.django_db
def test_team_email_records_the_consent(client):
    client.post(reverse("pages:contact"), _message(), **AJAX)

    team = next(m for m in mail.outbox if m.to == ["kontakt@monituj.pl"])
    assert "Zgoda na przetwarzanie danych: tak" in team.body.replace("\u00a0", " ")


@pytest.mark.django_db
def test_line_breaks_in_the_name_cannot_reach_the_subject(client):
    client.post(reverse("pages:contact"), _message(name="Jan\nBcc: x@y.pl"), **AJAX)

    team = next(m for m in mail.outbox if m.to == ["kontakt@monituj.pl"])
    assert "\n" not in team.subject


@pytest.mark.django_db
def test_bots_filling_the_hidden_field_get_success_but_nothing_is_sent(client):
    response = client.post(
        reverse("pages:contact"), _message(website="http://spam.example"), **AJAX
    )

    assert response.status_code == 200
    assert mail.outbox == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "bot",
    [
        {"seconds_ago": 1},  # faster than anyone types
        {"issued": "", "human": ""},  # posted without opening the page
        {"issued": "123:abc", "human": "cba:321"},  # a made-up token
        {"human": ""},  # the page's script never ran
        {"human": "something"},
    ],
    ids=["too-fast", "no-token", "forged-token", "no-script", "wrong-script"],
)
def test_bots_get_success_but_nothing_is_sent(client, bot):
    response = client.post(reverse("pages:contact"), _message(**bot), **AJAX)

    assert response.status_code == 200
    assert response.json()["success"]
    assert mail.outbox == []


@pytest.mark.django_db
def test_page_left_open_too_long_asks_to_reload_instead_of_dropping(client):
    seconds = int(MAX_AGE.total_seconds()) + 60

    response = client.post(
        reverse("pages:contact"), _message(seconds_ago=seconds), **AJAX
    )

    assert response.status_code == 400
    assert EXPIRED_MESSAGE in str(response.json())
    assert mail.outbox == []


@pytest.mark.django_db
def test_page_hands_out_a_token_and_the_script(client):
    page = client.get(reverse("pages:contact")).content.decode()

    token = page.split('name="issued" value="')[1].split('"')[0]
    assert isinstance(signing.loads(token, salt=TOKEN_SALT), int)
    assert '<input type="hidden" name="human" value="">' in page
    assert "js/contact.js" in page
    assert "<noscript>" in page and "kontakt@monituj.pl" in page


@pytest.mark.django_db
def test_form_is_limited_per_ip(client):
    for _ in range(LIMIT_PER_HOUR):
        client.post(reverse("pages:contact"), _message(), **AJAX)
    mail.outbox.clear()

    response = client.post(reverse("pages:contact"), _message(), **AJAX)

    assert response.status_code == 400
    assert "kontakt@monituj.pl" in response.json()["error"]["message"]
    assert mail.outbox == []


@pytest.mark.django_db
def test_without_javascript_the_form_redirects_with_a_message(client):
    response = client.post(reverse("pages:contact"), _message(), follow=True)

    assert "Odpowiemy najszybciej" in page_text(response)
    assert len(mail.outbox) == 2


@pytest.mark.django_db
def test_client_replies_to_request_emails_reach_the_firm(request_record, user):
    EmailService.send(
        EmailTemplate.REMINDER,
        to_email=request_record.client.email,
        request=request_record,
    )

    assert mail.outbox[0].reply_to == [user.email]


@pytest.mark.django_db
def test_account_emails_reply_to_the_team(user):
    EmailService.send(
        EmailTemplate.PASSWORD_CHANGED_NOTICE, to_email=user.email, context={}
    )

    assert "no-reply@monituj.pl" in mail.outbox[0].from_email
    assert mail.outbox[0].reply_to == ["kontakt@monituj.pl"]
