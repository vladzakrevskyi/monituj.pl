"""Zestawienie miesięczne, photos of pages as one PDF, "Dodaj inny dokument"
and the office's logo."""

import io
from datetime import timedelta

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accounts import branding
from apps.billing.models import BillingAccount
from apps.clients.models import Client
from apps.documents.models import Document
from apps.documents.pages import file_name
from apps.documents.services import UploadDocumentService
from apps.reminders.models import Reminder
from apps.requests import overview, questions
from apps.requests.models import Request, RequestItemStatus
from apps.requests.services import RequestService
from tests.conftest import make_pdf_upload, page_text


def _photo(name="strona.jpg", size=(1200, 1600), color=(240, 240, 240)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def _png(size=(400, 120)):
    buffer = io.BytesIO()
    image = Image.new("RGBA", (size[0] + 40, size[1] + 40), (0, 0, 0, 0))
    image.paste((255, 107, 0, 255), (20, 20, size[0] + 20, size[1] + 20))
    image.save(buffer, format="PNG")
    return SimpleUploadedFile("logo.png", buffer.getvalue(), content_type="image/png")


def _send(owner, client_record, name="Dokumenty", items=("Wyciąg", "Faktury"), **extra):
    return RequestService.create(
        owner=owner,
        client_id=client_record.pk,
        name=name,
        description="",
        deadline=extra.get("deadline"),
        item_names=list(items),
    )


def _open(client, request_obj):
    client.get(reverse("public:request-detail", args=[request_obj.public_token]))


# --- Zestawienie miesięczne -------------------------------------------------------


@pytest.fixture
def three_clients(user):
    return [
        Client.objects.create(owner=user, name=name, email=f"{slug}@example.com")
        for name, slug in [("Anna", "anna"), ("Bogdan", "bogdan"), ("Celina", "celina")]
    ]


@pytest.mark.django_db
def test_overview_sums_up_each_client_this_month(user, three_clients):
    anna, bogdan, celina = three_clients
    complete = _send(user, anna)
    for item in complete.items.all():
        UploadDocumentService.upload_for_item(item, make_pdf_upload(f"{item.pk}.pdf"))
    partial = _send(user, bogdan)
    UploadDocumentService.upload_for_item(partial.items.first(), make_pdf_upload())
    _send(user, celina, deadline=timezone.now() - timedelta(days=1))
    questions.ask(user, anna.pk, "Co to za przelew z 12.09?")  # not counted

    data = overview.build(user)

    cells = {row["client"].name: row["cells"][-1] for row in data["rows"]}
    assert cells["Anna"].state == overview.KOMPLET
    assert cells["Bogdan"].state == overview.BRAKUJE and cells["Bogdan"].missing == 1
    assert cells["Bogdan"].to_review == 1
    assert cells["Celina"].state == overview.PO_TERMINIE
    summary = data["summary"]
    assert (summary["clients"], summary["complete"], summary["waiting"]) == (3, 1, 2)
    assert summary["remindable"] == 2


@pytest.mark.django_db
def test_overview_puts_requests_in_the_month_they_were_sent(user, three_clients):
    old = _send(user, three_clients[0])
    Request.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=40)
    )
    _send(user, three_clients[1])

    data = overview.build(user)

    anna = next(r for r in data["rows"] if r["client"].name == "Anna")
    assert anna["cells"][-1].state == ""
    assert anna["cells"][-2].state == overview.NIC
    assert len(data["months"]) == overview.MONTHS


@pytest.mark.django_db
def test_overview_filters(user, three_clients):
    complete = _send(user, three_clients[0], items=("A",))
    UploadDocumentService.upload_for_item(complete.items.first(), make_pdf_upload())
    _send(user, three_clients[1])

    only = overview.build(user, only_missing=True)
    found = overview.build(user, query="anna")

    assert [r["client"].name for r in only["rows"]] == ["Bogdan"]
    assert [r["client"].name for r in found["rows"]] == ["Anna"]


@pytest.mark.django_db
def test_overview_page_and_remind_everyone(client, user, three_clients):
    _send(user, three_clients[0])
    _send(user, three_clients[1])
    client.force_login(user)
    page = page_text(client.get(reverse("requests:overview")))
    assert "Zestawienie miesięczne" in page and "Nic nie przysłał" in page
    month = overview.month_key(timezone.localdate())
    mail.outbox.clear()

    client.post(reverse("requests:overview-remind"), {"m": month})
    client.post(reverse("requests:overview-remind"), {"m": month})  # too soon

    assert Reminder.objects.count() == 2
    assert len(mail.outbox) == 2


@pytest.mark.django_db
def test_overview_remind_ignores_a_bad_month(client, user):
    client.force_login(user)

    response = client.post(reverse("requests:overview-remind"), {"m": "2026-13"})

    assert response["Location"] == reverse("requests:overview")


@pytest.mark.django_db
def test_overview_empty(client, user):
    client.force_login(user)

    page = page_text(client.get(reverse("requests:overview")))

    assert "Tu zobaczysz, kto jest na bieżąco" in page


# --- photos of pages as one PDF ---------------------------------------------------


@pytest.mark.django_db
def test_pages_become_one_pdf(client, request_item):
    request_obj = request_item.request
    _open(client, request_obj)
    url = reverse(
        "documents_api:upload-pages", args=[request_obj.public_token, request_item.pk]
    )

    response = client.post(
        url, {"pages": [_photo("1.jpg"), _photo("2.jpg"), _photo("3.jpg")]}
    )

    assert response.status_code == 201
    document = Document.objects.get()
    assert document.original_filename == "Faktury sprzedaży (3 str.).pdf"
    assert document.content_type == "application/pdf"
    request_item.refresh_from_db()
    assert request_item.status == RequestItemStatus.DOSTARCZONY


@pytest.mark.django_db
def test_pages_must_be_photos(client, request_item):
    request_obj = request_item.request
    _open(client, request_obj)
    url = reverse(
        "documents_api:upload-pages", args=[request_obj.public_token, request_item.pk]
    )

    response = client.post(url, {"pages": [make_pdf_upload()]})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PAGE_NOT_A_PHOTO"


@pytest.mark.django_db
def test_pages_need_at_least_one(client, request_item):
    request_obj = request_item.request
    _open(client, request_obj)
    url = reverse(
        "documents_api:upload-pages", args=[request_obj.public_token, request_item.pk]
    )

    response = client.post(url, {})

    assert response.json()["error"]["code"] == "NO_PAGES"


def test_pdf_name_is_safe():
    name = file_name('Wyciąg / bank: "PKO"', 2)

    assert not set(name) & set('\\/:*?"<>|')
    assert name.startswith("Wyciąg") and name.endswith("(2 str.).pdf")
    assert file_name("", 1) == "Dokument (1 str.).pdf"


# --- "Dodaj inny dokument" -----------------------------------------------------------


@pytest.mark.django_db
def test_client_adds_a_document_that_was_not_on_the_list(client, user, client_record):
    request_obj = _send(user, client_record)
    _open(client, request_obj)

    response = client.post(
        reverse("documents_api:add-extra", args=[request_obj.public_token]),
        {"name": "Faktura za paliwo", "file": make_pdf_upload()},
    )

    assert response.status_code == 201
    item = request_obj.items.get(added_by_client=True)
    assert item.name == "Faktura za paliwo"
    assert item.status == RequestItemStatus.DOSTARCZONY
    client.force_login(user)
    page = page_text(client.get(reverse("requests:detail", args=[request_obj.pk])))
    assert "dodane przez klienta" in page


@pytest.mark.django_db
def test_a_refused_extra_file_leaves_no_item(client, user, client_record):
    request_obj = _send(user, client_record)
    _open(client, request_obj)

    response = client.post(
        reverse("documents_api:add-extra", args=[request_obj.public_token]),
        {"name": "", "file": SimpleUploadedFile("x.exe", b"MZ" + b"0" * 100)},
    )

    assert response.status_code == 400
    assert not request_obj.items.filter(added_by_client=True).exists()


@pytest.mark.django_db
def test_extra_documents_have_a_limit_and_a_default_name(client, user, client_record):
    request_obj = _send(user, client_record)
    _open(client, request_obj)
    url = reverse("documents_api:add-extra", args=[request_obj.public_token])
    for number in range(10):
        client.post(url, {"file": make_pdf_upload(f"{number}.pdf")})

    response = client.post(url, {"file": make_pdf_upload("11.pdf")})

    assert response.json()["error"]["code"] == "TOO_MANY_EXTRA"
    assert request_obj.items.filter(name="Inny dokument").count() == 10


@pytest.mark.django_db
def test_no_extra_documents_on_a_question(client, user, client_record):
    asked = questions.ask(user, client_record.pk, "Co to za przelew z 12.09?")
    _open(client, asked)

    response = client.post(
        reverse("documents_api:add-extra", args=[asked.public_token]),
        {"file": make_pdf_upload()},
    )
    page = page_text(
        client.get(reverse("public:request-detail", args=[asked.public_token]))
    )

    assert response.json()["error"]["code"] == "NOT_FOR_QUESTIONS"
    assert "Dodaj inny dokument" not in page


# --- the office's logo ---------------------------------------------------------------


@pytest.mark.django_db
def test_logo_is_saved_trimmed_and_served(client, user):
    branding.save_logo(user, _png())

    logo = branding.logo_of(user)
    response = client.get(reverse("accounts:logo", args=[logo.key]))

    assert (logo.width, logo.height) == (400, 120)
    assert response["Content-Type"] == "image/png"
    assert "immutable" in response["Cache-Control"]


@pytest.mark.django_db
def test_not_an_image_is_refused(user):
    from apps.common.exceptions import ValidationAppError

    with pytest.raises(ValidationAppError):
        branding.save_logo(user, make_pdf_upload())


@pytest.mark.django_db
def test_clients_see_the_logo_on_a_paid_plan_only(client, user, client_record):
    branding.save_logo(user, _png())
    request_obj = _send(user, client_record)
    url = reverse("public:request-detail", args=[request_obj.public_token])
    logo_url = reverse("accounts:logo", args=[branding.logo_of(user).key])

    BillingAccount.objects.update_or_create(
        user=user, defaults={"trial_ends_at": timezone.now() + timedelta(days=10)}
    )
    on_trial = client.get(url).content.decode()
    BillingAccount.objects.filter(user=user).update(
        trial_ends_at=timezone.now() - timedelta(days=1)
    )
    on_free = client.get(url).content.decode()

    assert logo_url in on_trial
    assert logo_url not in on_free


@pytest.mark.django_db
def test_emails_to_clients_carry_the_logo(user, client_record):
    BillingAccount.objects.update_or_create(
        user=user, defaults={"trial_ends_at": timezone.now() + timedelta(days=10)}
    )
    branding.save_logo(user, _png())
    mail.outbox.clear()

    _send(user, client_record)

    html = mail.outbox[0].alternatives[0][0]
    assert reverse("accounts:logo", args=[branding.logo_of(user).key]) in html


@pytest.mark.django_db
def test_settings_upload_and_remove_the_logo(client, user):
    client.force_login(user)

    client.post(reverse("accounts:settings"), {"form_action": "logo", "logo": _png()})
    assert branding.logo_of(user) is not None
    client.post(reverse("accounts:settings"), {"form_action": "logo_remove"})

    assert branding.logo_of(user) is None
