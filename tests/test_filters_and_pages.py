from datetime import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.clients.models import Client
from apps.common.formatting import format_datetime
from apps.requests.forms import RequestForm
from apps.requests.models import Request, RequestItem, RequestItemStatus
from tests.conftest import page_text

AJAX_HEADERS = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def _request(owner, client, name, reminders=True, deadline=None):
    request_obj = Request.objects.create(
        client=client,
        created_by=owner,
        name=name,
        reminders_enabled=reminders,
        deadline=deadline,
    )
    RequestItem.objects.create(request=request_obj, name="Faktura")
    return request_obj


def test_format_datetime_uses_polish_genitive_month_and_local_time():
    value = timezone.make_aware(datetime(2026, 9, 25, 23, 59))
    assert format_datetime(value) == "25 września 2026 23:59"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({}, 90),
        ({"retention_choice": "30"}, 30),
        ({"retention_choice": "365"}, 365),
        ({"retention_choice": "custom", "retention_custom_days": "45"}, 45),
    ],
)
def test_request_form_retention_days(user, client_record, data, expected):
    form = RequestForm(
        data={"client": client_record.pk, "name": "R", **data}, owner=user
    )
    assert form.is_valid(), form.errors
    assert form.retention_days() == expected


@pytest.mark.django_db
@pytest.mark.parametrize("days", ["0", "366", ""])
def test_request_form_rejects_invalid_custom_retention(user, client_record, days):
    form = RequestForm(
        data={
            "client": client_record.pk,
            "name": "R",
            "retention_choice": "custom",
            "retention_custom_days": days,
        },
        owner=user,
    )
    assert not form.is_valid()
    assert "retention_custom_days" in form.errors


@pytest.mark.django_db
def test_request_create_stores_retention_days(client, user, client_record):
    client.force_login(user)
    response = client.post(
        reverse("requests:create"),
        {
            "client": client_record.pk,
            "name": "Z retencja",
            "items": ["A"],
            "retention_choice": "custom",
            "retention_custom_days": "120",
        },
        **AJAX_HEADERS,
    )
    assert response.status_code == 200
    assert Request.objects.get(name="Z retencja").retention_days == 120


@pytest.mark.django_db
def test_request_create_without_client_reports_error_on_client_field(client, user):
    client.force_login(user)
    response = client.post(
        reverse("requests:create"), {"name": "R", "items": ["A"]}, **AJAX_HEADERS
    )
    assert "client" in response.json()["error"]["fields"]


@pytest.mark.django_db
def test_request_list_filters_by_client_and_reminders(client, user, client_record):
    other = Client.objects.create(owner=user, name="Beta", email="b@example.com")
    _request(user, client_record, "Acme włączone")
    _request(user, client_record, "Acme wyłączone", reminders=False)
    _request(user, other, "Beta włączone")
    client.force_login(user)

    response = client.get(
        reverse("requests:list"), {"client": client_record.pk, "reminders": "on"}
    )

    names = [r.name for r in response.context["page_obj"].object_list]
    assert names == ["Acme włączone"]


@pytest.mark.django_db
def test_request_list_status_tabs_count_filtered_results(client, user, client_record):
    _request(user, client_record, "Brakujące")
    complete = _request(user, client_record, "Kompletne")
    complete.items.update(status=RequestItemStatus.ZAAKCEPTOWANY)
    client.force_login(user)

    response = client.get(reverse("requests:list"), {"status": "kompletny"})

    tabs = {t["code"]: t["count"] for t in response.context["status_tabs"]}
    assert tabs[""] == 2
    assert tabs["kompletny"] == 1
    assert [r.name for r in response.context["page_obj"].object_list] == ["Kompletne"]


@pytest.mark.django_db
def test_request_list_ignores_invalid_filter_values(client, user, client_record):
    _request(user, client_record, "Jedno")
    client.force_login(user)

    response = client.get(
        reverse("requests:list"),
        {"client": "999999", "deadline_from": "nie-data", "sort": "zle"},
    )

    assert response.status_code == 200
    assert len(response.context["page_obj"].object_list) == 1


@pytest.mark.django_db
def test_client_list_search_and_missing_filter(client, user, client_record):
    other = Client.objects.create(owner=user, name="Beta", email="b@example.com")
    _request(user, client_record, "Acme prośba")
    client.force_login(user)

    missing = client.get(reverse("clients:list"), {"missing": "yes"})
    search = client.get(reverse("clients:list"), {"q": "beta"})

    assert [c.name for c in missing.context["page_obj"].object_list] == [
        client_record.name
    ]
    assert [c.pk for c in search.context["page_obj"].object_list] == [other.pk]


@pytest.mark.django_db
def test_client_list_status_tab(client, user, client_record):
    Client.objects.create(owner=user, name="Pusty", email="p@example.com")
    _request(user, client_record, "Prośba")
    client.force_login(user)

    response = client.get(reverse("clients:list"), {"status": "nieaktywny"})

    assert [c.name for c in response.context["page_obj"].object_list] == ["Pusty"]


@pytest.mark.django_db
def test_client_documents_page_lists_all_and_missing(client, user, client_record):
    request_obj = _request(user, client_record, "Prośba")
    RequestItem.objects.create(
        request=request_obj, name="Dostarczony", status=RequestItemStatus.DOSTARCZONY
    )
    client.force_login(user)
    url = reverse("clients:documents", args=[client_record.pk])

    all_docs = client.get(url)
    missing = client.get(url, {"status": "brakujace"})

    assert len(all_docs.context["page_obj"].object_list) == 2
    assert [i.name for i in missing.context["page_obj"].object_list] == ["Faktura"]


@pytest.mark.django_db
def test_client_documents_page_is_owner_scoped(client, client_record):
    stranger = User.objects.create_user(email="obcy@example.com", password="x-Pass!1")
    client.force_login(stranger)

    response = client.get(reverse("clients:documents", args=[client_record.pk]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_client_create_flashes_success_message(client, user):
    client.force_login(user)
    client.post(
        reverse("clients:create"),
        {"name": "Nowy", "email": "nowy@example.com"},
        **AJAX_HEADERS,
    )

    response = client.get(reverse("clients:list"))

    assert "Klient został dodany.".encode() in response.content


@pytest.mark.django_db
def test_client_edit_ajax_reports_field_errors(client, user, client_record):
    client.force_login(user)

    response = client.post(
        reverse("clients:edit", args=[client_record.pk]),
        {"name": "", "email": "zly"},
        **AJAX_HEADERS,
    )

    fields = response.json()["error"]["fields"]
    assert "name" in fields
    assert "email" in fields


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["terms", "privacy", "cookies", "dpa"])
def test_legal_pages_render_with_placeholders(client, settings, name):
    settings.LEGAL_ENTITY = {}
    response = client.get(reverse(f"legal:{name}"))
    assert response.status_code == 200
    assert b"legal-todo" in response.content


@pytest.mark.django_db
def test_legal_pages_use_configured_company_details(client, settings):
    settings.LEGAL_ENTITY = {"name": "Monituj Sp. z o.o.", "email": "hej@monituj.pl"}
    response = client.get(reverse("legal:terms"))
    assert "Monituj Sp. z o.o." in page_text(response)
    assert b"hej@monituj.pl" in response.content
