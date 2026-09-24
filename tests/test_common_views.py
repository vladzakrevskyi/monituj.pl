import pytest
from django.core import mail
from django.urls import reverse

from apps.common.content import FAQ, SEGMENTS
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService
from tests.conftest import page_text

PUBLIC_PAGES = [
    "pages:how-it-works",
    "pages:features",
    "pages:for-whom",
    "pages:security",
    "pages:pricing",
    "pages:faq",
    "pages:contact",
    "pages:demo",
]


@pytest.mark.django_db
def test_landing_page_renders_for_anonymous_visitor(client):
    response = client.get("/")

    content = page_text(response)
    assert response.status_code == 200
    assert "pilnuje" in content
    assert reverse("accounts:register") in content
    assert "Zacznij za darmo" in content


@pytest.mark.django_db
def test_landing_page_does_not_redirect_authenticated_user(client, user):
    client.force_login(user)

    response = client.get("/")

    assert response.status_code == 200
    assert "Przejdź do panelu" in page_text(response)


@pytest.mark.django_db
def test_landing_page_links_to_guest_request_create(client):
    response = client.get("/")

    assert reverse("public:guest-request-create").encode() in response.content


@pytest.mark.django_db
def test_landing_page_shows_only_home_faq_items(client):
    content = page_text(client.get("/"))

    for item in FAQ:
        assert (item["q"] in content) == item["home"]


@pytest.mark.django_db
@pytest.mark.parametrize("name", PUBLIC_PAGES)
def test_public_pages_render_and_are_linked_from_landing(client, name):
    response = client.get(reverse(name))

    assert response.status_code == 200
    landing = client.get("/").content.decode()
    assert reverse(name) in landing


@pytest.mark.django_db
def test_for_whom_page_lists_every_segment_with_anchor(client):
    content = page_text(client.get(reverse("pages:for-whom")))

    for segment in SEGMENTS:
        assert f'id="{segment["slug"]}"' in content
        assert segment["title"] in content


@pytest.mark.django_db
def test_faq_page_shows_every_question(client):
    content = page_text(client.get(reverse("pages:faq")))

    for item in FAQ:
        assert item["q"] in content


@pytest.mark.django_db
def test_active_page_is_marked_in_navigation(client):
    content = client.get(reverse("pages:features")).content.decode()

    assert f'href="{reverse("pages:features")}" class="is-active"' in content


@pytest.mark.django_db
def test_every_email_is_sent_as_html_with_text_fallback(request_record, request_item):
    for template in EmailTemplate:
        EmailService.send(
            template,
            to_email="klient@example.com",
            context={
                "count": 1,
                "password": "Sekret-1",
                "document_name": "plik.pdf",
                "item_name": "Faktura",
                "reason": "Nieczytelny",
                "new_email": "nowy@example.com",
                "verification_url": "http://x/v/",
                "reset_url": "http://x/r/",
                "confirm_url": "http://x/c/",
                "contact_name": "Jan Kowalski",
                "contact_email": "jan@example.com",
                "contact_topic": "Pytanie o Monituj",
                "contact_message": "Dzień dobry,\ndruga linia.",
            },
            request=request_record,
        )

    assert len(mail.outbox) == len(EmailTemplate)
    for message in mail.outbox:
        html, mimetype = message.alternatives[0]
        assert mimetype == "text/html"
        assert "<!DOCTYPE html>" in html
        assert "Monituj" in html
        assert message.body.strip()


@pytest.mark.django_db
def test_request_emails_link_to_the_upload_page_and_list_missing_items(
    request_record, request_item
):
    EmailService.send(
        EmailTemplate.REMINDER, to_email="klient@example.com", request=request_record
    )

    message = mail.outbox[0]
    html = message.alternatives[0][0]
    assert f"/d/{request_record.public_token}/" in message.body
    assert f"/d/{request_record.public_token}/" in html
    assert request_item.name in message.body
    assert request_item.name in html


@pytest.mark.django_db
def test_plain_text_email_parts_are_not_html_escaped(request_record, request_item):
    request_record.name = 'Faktury & umowy "Q3"'
    request_record.save()

    EmailService.send(
        EmailTemplate.REMINDER, to_email="klient@example.com", request=request_record
    )

    message = mail.outbox[0]
    assert 'Faktury & umowy "Q3"' in message.body
    assert "&amp;" not in message.body
    assert "&amp;" in message.alternatives[0][0]
