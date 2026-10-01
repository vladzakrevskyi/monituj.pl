"""Importing clients from a CSV or Excel file: read, guess the columns,
preview, import - and the NIP a client now has."""

import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.audit.models import AuditEvent, AuditLog
from apps.clients import importing
from apps.clients.models import Client, ClientImport
from tests.conftest import page_text

NIP = "5213017228"


def _csv(text, encoding="utf-8", name="klienci.csv"):
    return SimpleUploadedFile(name, text.encode(encoding), content_type="text/csv")


def _xlsx(rows, name="klienci.xlsx"):
    from openpyxl import Workbook

    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return SimpleUploadedFile(name, buffer.getvalue())


def _upload(client, upload):
    response = client.post(reverse("clients:import"), {"file": upload})
    assert response.status_code == 302, response.content.decode()[:2000]
    return response.url


# --- reading and guessing ---------------------------------------------------------


def test_polish_excel_csv_in_windows_1250_with_semicolons():
    upload = _csv(
        "Nazwa kontrahenta;Adres e-mail;Telefon;NIP\n"
        "Łąkowa Sp. z o.o.;biuro@lakowa.pl;600 100 200;521-301-72-28\n",
        encoding="cp1250",
    )

    table = importing.read_table(upload)

    assert table[1][0] == "Łąkowa Sp. z o.o."
    assert importing.has_header(table)
    assert importing.guess_mapping(table, True) == ["name", "email", "phone", "nip"]


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16", "cp1250", "mac_latin2"])
def test_every_encoding_excel_saves_in(encoding):
    """Excel on a Mac saves "CSV" and tab-separated text in Mac Central
    European, on Windows in Windows-1250, "Tekst Unicode" in UTF-16."""
    text = "Nazwa\tE-mail\r\nKowalski Usługi Remontowe\tbiuro@example.com\r\n"
    table = importing.read_table(_csv(text, encoding=encoding))

    assert table == [
        ["Nazwa", "E-mail"],
        ["Kowalski Usługi Remontowe", "biuro@example.com"],
    ]


def test_columns_found_by_content_without_headers():
    table = importing.read_table(
        _csv(f"Kowalski,{NIP},jan@example.com\nNowak,,anna@example.com\n")
    )

    assert not importing.has_header(table)
    assert importing.guess_mapping(table, False) == ["name", "nip", "email"]


def test_the_firms_own_people_are_not_the_client():
    table = [["Nazwa1", "E-mail opiekuna", "Opiekun klienta", "E-mail"], ["A"] * 4]

    assert importing.guess_mapping(table, True) == ["name", "", "", "email"]


def test_an_xlsx_unpacking_too_big_is_refused():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/sharedStrings.xml", "a" * (60 * 1024 * 1024))

    with pytest.raises(importing.FileProblem):
        importing.read_table(SimpleUploadedFile("bomba.xlsx", buffer.getvalue()))


def test_excel_numbers_come_as_text():
    table = importing.read_table(
        _xlsx([["Firma", "Email", "NIP", "Tel"], ["A", "a@x.pl", int(NIP), 600100200]])
    )

    assert table[1] == ["A", "a@x.pl", NIP, "600100200"]


@pytest.mark.parametrize(
    ("upload", "message"),
    [
        (_csv("", name="pusty.csv"), "pusty"),
        (SimpleUploadedFile("stary.xls", b"x"), ".xls"),
        (SimpleUploadedFile("lista.pdf", b"x"), "CSV albo XLSX"),
        (SimpleUploadedFile("zly.xlsx", b"to nie jest zip"), "Nie udało się"),
        (_csv("Nazwa;Email\n" + "A;a@x.pl\n" * 1001), "więcej niż 1000"),
    ],
)
def test_files_that_cannot_be_imported(upload, message):
    with pytest.raises(importing.FileProblem) as error:
        importing.read_table(upload)

    assert message in error.value.message


# --- preview and import ---------------------------------------------------------


@pytest.mark.django_db
def test_preview_then_import(client, user, client_record):
    client.force_login(user)
    url = _upload(
        client,
        _csv(
            "Nazwa;E-mail;NIP;Uwagi\n"
            f"Nowa firma;nowa@example.com;{NIP};VAT\n"
            f"Już jest;{client_record.email};;\n"
            "Zły adres;to-nie-email;;\n"
            ";bez-nazwy@example.com;123;\n"
            "Powtórka;NOWA@example.com;;\n"
        ),
    )

    page = page_text(client.get(url))
    assert "Dodamy <strong>2</strong> klientów" in page
    assert "Nieprawidłowy NIP „123” - dodamy klienta bez NIP." in page
    assert "Ten sam adres co w wierszu 2. Pominiemy ten wiersz." in page
    assert Client.objects.filter(owner=user).count() == 1  # nothing saved yet

    response = client.post(
        url, {"naglowek": "1", "kolumna": ["name", "email", "nip", "note"]}
    )

    assert response.url == reverse("clients:list")
    added = Client.objects.get(email="nowa@example.com")
    assert (added.name, added.nip, added.note) == ("Nowa firma", NIP, "VAT")
    assert Client.objects.get(email="bez-nazwy@example.com").name == "bez-nazwy"
    assert Client.objects.filter(owner=user).count() == 3
    assert not ClientImport.objects.exists()
    entry = AuditLog.objects.get(event=AuditEvent.CLIENTS_IMPORTED)
    assert entry.metadata == {"created": 2, "updated": 0, "skipped": 3}
    # A second click finds nothing to import again.
    again = client.post(url, {"naglowek": "1"})
    assert again.url == reverse("clients:list")
    assert Client.objects.filter(owner=user).count() == 3


@pytest.mark.django_db
def test_existing_clients_filled_in_only_when_asked(client, user, client_record):
    client_record.phone = "111"
    client_record.save()
    client.force_login(user)
    text = f"Nazwa;Email;Telefon;NIP\nNowa nazwa;{client_record.email};;{NIP}\n"

    client.post(_upload(client, _csv(text)), {"istniejacy": "pomin"})
    client_record.refresh_from_db()
    assert client_record.nip == ""

    client.post(_upload(client, _csv(text)), {"istniejacy": "aktualizuj"})
    client_record.refresh_from_db()
    assert (client_record.name, client_record.nip) == ("Nowa nazwa", NIP)
    assert client_record.phone == "111"  # an empty cell changes nothing


@pytest.mark.django_db
def test_columns_corrected_on_the_preview(client, user):
    client.force_login(user)
    # One address among notes - too few to tell it's the email column.
    url = _upload(client, _csv("Kod;Kontakt\nA;a@example.com\nB;brak\nC;brak\n"))

    page = page_text(client.get(url))
    assert "Wskaż kolumnę z adresem e-mail" in page

    choice = {"naglowek": "1", "kolumna": ["name", "email"]}
    assert "Wskaż kolumnę" not in page_text(client.get(url, choice))
    client.post(url, choice)
    assert Client.objects.get(owner=user).name == "A"


@pytest.mark.django_db
def test_no_import_without_an_email_column(client, user):
    client.force_login(user)
    url = _upload(client, _csv("Nazwa;Email\nA;a@example.com\n"))

    response = client.post(url, {"naglowek": "1", "kolumna": ["name", ""]})

    assert response.status_code == 200
    assert not Client.objects.exists()


@pytest.mark.django_db
def test_someone_elses_import_is_not_found(client, user):
    from apps.accounts.models import User

    other = User.objects.create_user(email="inny@example.com", password="x")
    draft = ClientImport.objects.create(
        owner=other, file_name="x.csv", table=[["Email"], ["a@example.com"]]
    )
    client.force_login(user)

    url = reverse("clients:import-preview", args=[draft.pk])
    assert client.get(url).status_code == 404
    client.post(url)
    assert not Client.objects.exists()


@pytest.mark.django_db
def test_upload_page_and_sample(client, user):
    client.force_login(user)

    assert "Importuj z pliku" in client.get(reverse("clients:list")).content.decode()
    page = client.get(reverse("clients:import")).content.decode()
    assert 'enctype="multipart/form-data"' in page
    sample = client.get(reverse("clients:import-sample"))
    table = importing.read_table(_csv(sample.content.decode("utf-8-sig")))
    assert importing.guess_mapping(table, True) == [
        "name",
        "email",
        "phone",
        "nip",
        "note",
    ]


@pytest.mark.django_db
def test_upload_error_shown_on_the_form(client, user):
    client.force_login(user)

    response = client.post(
        reverse("clients:import"), {"file": SimpleUploadedFile("a.xls", b"x")}
    )

    assert response.status_code == 200
    assert "Starszy format Excela" in page_text(response)


@pytest.mark.django_db
def test_old_drafts_are_cleaned(user):
    from datetime import timedelta

    from django.utils import timezone

    from apps.clients.tasks import delete_old_client_imports

    old = ClientImport.objects.create(owner=user, file_name="a.csv", table=[["a"]])
    ClientImport.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=2)
    )
    fresh = ClientImport.objects.create(owner=user, file_name="b.csv", table=[["b"]])

    assert delete_old_client_imports() == 1
    assert list(ClientImport.objects.all()) == [fresh]


# --- NIP on the client -------------------------------------------------------------


@pytest.mark.django_db
def test_client_form_checks_and_cleans_the_nip(client, user):
    client.force_login(user)

    bad = client.post(
        reverse("clients:create"),
        {"name": "A", "email": "a@example.com", "nip": "1234567890"},
    )
    assert "Nieprawidłowy NIP." in page_text(bad)

    client.post(
        reverse("clients:create"),
        {"name": "A", "email": "a@example.com", "nip": "PL 521-301-72-28"},
    )
    assert Client.objects.get(owner=user).nip == NIP


@pytest.mark.django_db
def test_clients_found_by_nip(client, user, client_record):
    client_record.nip = NIP
    client_record.save()
    Client.objects.create(owner=user, name="Inny", email="inny@example.com")
    client.force_login(user)

    page = client.get(reverse("clients:list"), {"q": "521-301"}).content.decode()

    assert client_record.name in page and "Inny" not in page
    assert f"NIP {NIP}" in page
