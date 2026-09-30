"""Request templates: saving them (while sending, from a sent request, from
a ready one), filling the form from them, the plan's limit from the new
Regulamin on, and the public library that search engines index."""

import json
import re
from datetime import date, timedelta

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.services import welcome_url
from apps.clients.models import Client
from apps.common.content import SEGMENTS
from apps.consents.models import AcceptanceMethod
from apps.consents.services import record_acceptance
from apps.requests import request_templates, template_library
from apps.requests.models import Request, RequestTemplate
from tests.conftest import page_text
from tests.test_billing import _expire_trial

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


@pytest.fixture
def client_record(user):
    return Client.objects.create(owner=user, name="Klient", email="k@example.com")


@pytest.fixture
def limits_on(settings, monkeypatch):
    """The Regulamin with per-plan template limits is in force."""
    monkeypatch.setattr(request_templates, "TEMPLATE_LIMITS_SINCE", date(2026, 1, 1))
    settings.LEGAL_VERSIONS = {**settings.LEGAL_VERSIONS, "regulamin": "2026-01-02"}


def _send(client, **data):
    base = {
        "name": "Dokumenty za {miesiąc}",
        "items": ["Faktury", "Wyciągi bankowe"],
        "retention_choice": "90",
        "reminder_preset": "frequent",
        "deadline_choice": "7",
    }
    return client.post(reverse("requests:create"), {**base, **data}, **AJAX)


def _own(user, title="Miesięczne", **fields):
    return RequestTemplate.objects.create(
        owner=user,
        title=title,
        name=fields.pop("name", "Dokumenty za {miesiąc}"),
        item_names=fields.pop("item_names", ["Faktury", "Wyciągi"]),
        **fields,
    )


def _prefilled_items(response):
    match = re.search(
        r'<script id="posted-items-data" type="application/json">(.*?)</script>',
        page_text(response),
        re.S,
    )
    return json.loads(match.group(1))


# --- saving ------------------------------------------------------------------


@pytest.mark.django_db
def test_ticking_save_as_template_keeps_the_list_and_the_settings(
    client, user, client_record
):
    client.force_login(user)

    response = _send(
        client,
        clients=[client_record.pk],
        save_as_template="on",
        template_title="Miesięczne - KPiR",
    )

    assert response.status_code == 200
    template = RequestTemplate.objects.get(owner=user)
    assert template.title == "Miesięczne - KPiR"
    # The template keeps {miesiąc}; the one-off request got the month itself.
    assert template.name == "Dokumenty za {miesiąc}"
    assert "{" not in Request.objects.get().name
    assert template.item_names == ["Faktury", "Wyciągi bankowe"]
    assert template.deadline_choice == "7"
    assert (template.first_reminder_after_days, template.max_reminders) == (1, 5)


@pytest.mark.django_db
def test_a_taken_template_title_stops_the_form_before_anything_is_sent(
    client, user, client_record
):
    _own(user, title="Miesięczne")
    client.force_login(user)

    response = _send(
        client,
        clients=[client_record.pk],
        save_as_template="on",
        template_title="miesięczne",
    )

    assert "template_title" in response.json()["error"]["fields"]
    assert not Request.objects.exists()


@pytest.mark.django_db
def test_save_a_sent_request_as_a_template(client, user, client_record):
    request_obj = Request.objects.create(
        client=client_record,
        created_by=user,
        name="Dokumenty kadrowe",
        deadline=timezone.now() + timedelta(days=21),
        max_reminders=5,
    )
    request_obj.items.create(name="Umowa")
    client.force_login(user)

    response = client.post(
        reverse("requests:template-from-request", args=[request_obj.pk])
    )

    template = RequestTemplate.objects.get(owner=user)
    assert response.url == reverse("requests:template-edit", args=[template.pk])
    assert template.item_names == ["Umowa"]
    assert (template.deadline_choice, template.deadline_days) == ("days", 21)
    assert template.max_reminders == 5


@pytest.mark.django_db
def test_someone_elses_request_or_template_is_not_found(client, user, client_record):
    other = User.objects.create_user(email="inny@example.com", password="x")
    request_obj = Request.objects.create(
        client=client_record, created_by=user, name="Moja"
    )
    template = _own(user)
    client.force_login(other)

    assert (
        client.post(
            reverse("requests:template-from-request", args=[request_obj.pk])
        ).status_code
        == 404
    )
    assert (
        client.get(reverse("requests:template-edit", args=[template.pk])).status_code
        == 404
    )
    assert (
        client.post(reverse("requests:template-delete", args=[template.pk])).status_code
        == 404
    )
    # ?szablon= with someone else's id fills nothing.
    page = client.get(reverse("requests:create"), {"szablon": template.pk})
    assert _prefilled_items(page) == []


@pytest.mark.django_db
def test_edit_and_delete_own_template(client, user):
    template = _own(user)
    client.force_login(user)

    client.post(
        reverse("requests:template-edit", args=[template.pk]),
        {
            "title": "Kwartalne",
            "name": "Dokumenty za kwartał",
            "items": ["Faktury", "Umowy"],
            "deadline_choice": "days",
            "deadline_days": "30",
            "reminder_preset": "gentle",
            "retention_choice": "180",
        },
    )
    template.refresh_from_db()
    assert (template.title, template.item_names) == ("Kwartalne", ["Faktury", "Umowy"])
    assert (template.deadline_choice, template.deadline_days) == ("days", 30)
    assert template.retention_days == 180

    client.post(reverse("requests:template-delete", args=[template.pk]))
    assert not RequestTemplate.objects.exists()


# --- using -------------------------------------------------------------------


@pytest.mark.django_db
def test_own_template_fills_the_new_request_form(client, user):
    template = _own(
        user, deadline_choice="day10", first_reminder_after_days=1, max_reminders=5
    )
    client.force_login(user)

    page = client.get(reverse("requests:create"), {"szablon": template.pk})

    text = page_text(page)
    assert _prefilled_items(page) == ["Faktury", "Wyciągi"]
    assert 'value="Dokumenty za {miesiąc}"' in text
    assert 'name="deadline_choice" value="day10" checked' in text
    assert 'name="reminder_preset" value="custom" checked' in text
    template.refresh_from_db()
    assert template.last_used_at is not None


@pytest.mark.django_db
def test_ready_template_fills_the_form_and_suggests_repeating(client, user):
    client.force_login(user)
    ready = template_library.get("dokumenty-ksiegowe-za-miesiac")

    page = client.get(reverse("requests:create"), {"szablon": ready.slug})

    assert _prefilled_items(page) == ready.item_names
    assert "Powtarzaj automatycznie" in page_text(page)
    assert "zwykle wysyła się co miesiąc" in page_text(page)


@pytest.mark.django_db
def test_a_day_count_becomes_a_date_for_a_one_off_request(client, user):
    template = _own(user, deadline_choice="days", deadline_days=21)
    client.force_login(user)

    page = page_text(client.get(reverse("requests:create"), {"szablon": template.pk}))

    expected = (timezone.localdate() + timedelta(days=21)).isoformat()
    assert f'value="{expected}"' in page
    assert 'name="deadline_choice" value="date" checked' in page


@pytest.mark.django_db
def test_copy_a_ready_template_to_change_it(client, user):
    client.force_login(user)

    client.post(reverse("requests:template-copy", args=["kredyt-hipoteczny"]))
    client.post(reverse("requests:template-copy", args=["kredyt-hipoteczny"]))

    assert list(
        RequestTemplate.objects.order_by("id").values_list("title", flat=True)
    ) == ["Kredyt hipoteczny", "Kredyt hipoteczny (2)"]


# --- limits ------------------------------------------------------------------


@pytest.mark.django_db
def test_no_plan_limit_before_the_new_regulamin(client, user):
    for number in range(3):
        _own(user, title=f"Szablon {number}")

    usage = request_templates.usage(user)

    assert usage["plan"] is None
    assert usage["limit"] == request_templates.TECHNICAL_LIMIT
    assert not usage["at_limit"]


@pytest.mark.django_db
def test_free_plan_keeps_one_template_once_the_regulamin_applies(
    client, user, client_record, limits_on
):
    _expire_trial(user)
    record_acceptance(user, AcceptanceMethod.REGISTRATION)
    _own(user)
    client.force_login(user)

    usage = request_templates.usage(user)
    assert (usage["plan"].code, usage["limit"], usage["at_limit"]) == ("free", 1, True)

    refused = _send(client, clients=[client_record.pk], save_as_template="on")
    assert "save_as_template" in refused.json()["error"]["fields"]
    assert not Request.objects.exists()

    new_page = client.get(reverse("requests:template-create"))
    assert new_page.url == reverse("requests:templates")
    client.post(reverse("requests:template-copy", args=["kredyt-hipoteczny"]))
    assert RequestTemplate.objects.count() == 1
    # The one already saved still works.
    page = client.get(reverse("requests:create"), {"szablon": _own_id(user)})
    assert _prefilled_items(page) == ["Faktury", "Wyciągi"]


def _own_id(user):
    return RequestTemplate.objects.get(owner=user).pk


@pytest.mark.django_db
def test_trial_has_the_biuro_limit(user, limits_on):
    usage = request_templates.usage(user)

    assert (usage["plan"].code, usage["limit"]) == ("biuro", 20)


# --- the public library ------------------------------------------------------


def test_three_ready_templates_for_every_industry():
    for segment in SEGMENTS:
        assert len(template_library.for_segment(segment["slug"])) == 3
    slugs = [t.slug for t in template_library.TEMPLATES]
    assert len(slugs) == len(set(slugs))
    for template in template_library.TEMPLATES:
        assert template.deadline in ("7", "14", "day10", "none")
        assert 0 < len(template.summary) <= 155
        assert all(0 < len(name) <= 255 for name, _ in template.items)


@pytest.mark.django_db
def test_library_and_template_pages_are_indexed(client):
    library = client.get(reverse("pages:templates"))
    page = client.get(reverse("pages:template", args=["sprawa-spadkowa"]))

    assert library.status_code == page.status_code == 200
    for template in template_library.TEMPLATES:
        assert template.title in page_text(library)
    text = page_text(page)
    assert "Odpis skrócony aktu zgonu spadkodawcy" in text
    assert '"@type": "ItemList"' in text
    assert 'content="index, follow' in text
    assert client.get(reverse("pages:template", args=["nie-ma"])).status_code == 404

    sitemap = page_text(client.get("/sitemap.xml"))
    assert "/szablony/sprawa-spadkowa/" in sitemap
    assert "/szablony/sprawa-spadkowa/" in page_text(client.get("/llms.txt"))


@pytest.mark.django_db
def test_segment_page_shows_its_ready_templates(client):
    text = page_text(client.get(reverse("pages:segment", args=["kadry"])))

    assert "/szablony/zatrudnienie-cudzoziemca/" in text


@pytest.mark.django_db
def test_template_picked_before_signing_up_opens_after(rf, client, user):
    client.get(reverse("accounts:register"), {"szablon": "umowa-zlecenia"})
    assert client.session[request_templates.SIGNUP_SESSION_KEY] == "umowa-zlecenia"

    request = rf.get("/")
    request.session = SessionStore()
    request.session[request_templates.SIGNUP_SESSION_KEY] = "umowa-zlecenia"
    request._messages = type("M", (), {"add": lambda *a, **k: None})()

    assert welcome_url(request, user) == (
        f"{reverse('requests:create')}?szablon=umowa-zlecenia"
    )
    assert request_templates.SIGNUP_SESSION_KEY not in request.session


@pytest.mark.django_db
def test_visitor_without_account_gets_the_ready_template(client):
    page = client.get(
        reverse("public:guest-request-create"), {"szablon": "sprzedaz-mieszkania"}
    )

    assert (
        _prefilled_items(page) == template_library.get("sprzedaz-mieszkania").item_names
    )
    assert 'value="Dokumenty do sprzedaży mieszkania"' in page_text(page)
