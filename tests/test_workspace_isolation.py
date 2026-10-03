"""Nothing of one firm is reachable from another: every panel and API
address that takes an object id is tried, with GET and POST, with the ids
of a firm the person isn't in - from a team's workspace and from their own
account. Each answer must be a refusal and nothing of the other firm may
change. New addresses with ids are covered automatically."""

from datetime import date

import pytest
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from django.utils import timezone

from apps.accounts import team
from apps.accounts.models import TeamMembership, User
from apps.billing.models import VatInvoice
from apps.clients.models import Client
from apps.documents.models import Document
from apps.documents.services import UploadDocumentService
from apps.requests.models import RecurringRequest, Request, RequestTemplate
from tests.conftest import make_pdf_upload

REFUSED = {302, 400, 403, 404, 405}
# Recipients' side: reached by the request's secret link, not by ids.
PUBLIC = {"upload", "public-not-applicable", "public-delete"}


def _id_routes():
    def walk(patterns, prefix="", namespace=""):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                yield from walk(
                    pattern.url_patterns,
                    prefix + str(pattern.pattern),
                    pattern.namespace or namespace,
                )
            elif isinstance(pattern, URLPattern):
                route = prefix + str(pattern.pattern)
                if "<int:" in route or "<uuid:" in route:
                    yield namespace, pattern.name, pattern.pattern.converters

    return list(walk(get_resolver().url_patterns))


@pytest.fixture
def other_firm(db):
    """A firm with one of everything."""
    owner = User.objects.create_user(
        email="inna@firma.pl", password="x", email_verified_at=timezone.now()
    )
    client = Client.objects.create(owner=owner, name="Cudzy", email="c@example.com")
    request = Request.objects.create(client=client, created_by=owner, name="Cudza")
    item = request.items.create(name="Faktury")
    document = UploadDocumentService.upload_for_item(item, make_pdf_upload())
    template = RequestTemplate.objects.create(
        owner=owner, title="Cudzy szablon", name="X", item_names=["A"]
    )
    schedule = RecurringRequest.objects.create(
        owner=owner,
        name="Cudza cykliczna",
        item_names=["A"],
        month_day=1,
        next_due_on=date(2026, 11, 1),
        next_run_on=date(2026, 11, 2),
    )
    schedule.clients.set([client])
    invoice = VatInvoice.objects.create(
        user=owner,
        email=owner.email,
        stripe_mode="sandbox",
        stripe_invoice_id="in_cudza",
        description="Plan",
        gross=100,
        paid_at=timezone.now(),
    )
    from apps.clients.models import ClientImport

    draft = ClientImport.objects.create(
        owner=owner, file_name="x.csv", table=[["Email"], ["a@example.com"]]
    )
    return {
        "owner": owner,
        "client_id": client.pk,
        "request_id": request.pk,
        "item_id": item.pk,
        "document_id": document.pk,
        "template_id": template.pk,
        "schedule_id": schedule.pk,
        "invoice_id": invoice.pk,
        "import_id": draft.pk,
    }


def _snapshot(firm):
    owner = firm["owner"]
    return (
        Client.objects.filter(owner=owner).count(),
        Request.objects.filter(created_by=owner, closed_at__isnull=True).count(),
        list(
            Request.objects.filter(created_by=owner).values_list(
                "name", "items__status"
            )
        ),
        Document.objects.filter(request_item__request__created_by=owner).count(),
        RequestTemplate.objects.filter(owner=owner).count(),
        list(
            RecurringRequest.objects.filter(owner=owner).values_list("active", "name")
        ),
    )


@pytest.mark.django_db
@pytest.mark.parametrize("workspace", ["team", "own"])
def test_no_address_reaches_another_firm(client, user, other_firm, workspace):
    person = User.objects.create_user(
        email="anna@biuro.pl", password="x", email_verified_at=timezone.now()
    )
    TeamMembership.objects.create(owner=user, user=person)
    client.force_login(person)
    if workspace == "team":
        client.post(reverse("accounts:workspace"), {"owner": user.pk})
    before = _snapshot(other_firm)

    tried = 0
    for namespace, name, converters in _id_routes():
        if name in PUBLIC:
            continue
        kwargs = {key: other_firm[key] for key in converters if key in other_firm}
        if set(kwargs) != set(converters):
            continue  # a token-based address
        url = reverse(f"{namespace}:{name}", kwargs=kwargs)
        for method in ("get", "post", "delete"):
            response = getattr(client, method)(url)
            ok = response.status_code in REFUSED
            if response.status_code == 302:
                # Only away from the object - never into it.
                ok = str(other_firm[next(iter(kwargs))]) not in response.url
            assert ok, f"{method.upper()} {url} -> {response.status_code}"
            tried += 1

    assert tried > 40
    assert _snapshot(other_firm) == before
    # Not even by switching into it.
    client.post(reverse("accounts:workspace"), {"owner": other_firm["owner"].pk})
    assert client.get(reverse("clients:list")).content.decode().count("Cudzy") == 0


@pytest.mark.django_db
def test_switching_into_a_firm_one_isnt_in_does_nothing(client, user, other_firm):
    client.force_login(user)

    client.post(reverse("accounts:workspace"), {"owner": other_firm["owner"].pk})

    assert client.session.get(team.SESSION_KEY) is None


@pytest.mark.django_db
def test_switching_needs_csrf(user, other_firm):
    from django.test import Client as HttpClient

    browser = HttpClient(enforce_csrf_checks=True)
    browser.force_login(user)

    response = browser.post(reverse("accounts:workspace"), {"owner": user.pk})

    assert response.status_code == 403
