"""Klienci → Importuj z pliku: upload, the preview with the columns to
correct, then the import (apps/clients/importing.py)."""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts import team
from apps.clients import importing
from apps.clients.models import ClientImport
from apps.common import throttle
from apps.common.exceptions import ApplicationError

UPLOADS_PER_HOUR = 30
# The new clients shown on the preview - enough to see the columns are right.
SAMPLE_ROWS = 10


class ImportFileForm(forms.Form):
    file = forms.FileField(
        label="Plik z klientami",
        error_messages={"required": "Wybierz plik CSV albo XLSX."},
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,.xlsx,.txt,text/csv"}),
    )


@login_required
@require_http_methods(["GET", "POST"])
def client_import(request):
    form = ImportFileForm()
    if request.method == "POST":
        form = ImportFileForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["file"]
            try:
                throttle.consume(
                    f"client-import:{request.user.pk}", UPLOADS_PER_HOUR, throttle.HOUR
                )
                table = importing.read_table(uploaded)
            except ApplicationError as exc:
                form.add_error("file", exc.message)
            else:
                ClientImport.objects.filter(owner=request.user).delete()
                draft = ClientImport.objects.create(
                    owner=request.user,
                    account=request.account,
                    file_name=uploaded.name[:255],
                    table=table,
                )
                return redirect("clients:import-preview", import_id=draft.pk)
    return render(
        request,
        "clients/import.html",
        {"form": form, "max_rows": importing.MAX_ROWS},
    )


def _read_choices(params, draft):
    """The header flag and the column mapping - as the owner set them on
    the preview, else as guessed."""
    table = draft.table
    width = len(table[0])
    if "naglowek" in params:
        header = params.get("naglowek") == "1"
    else:
        header = importing.has_header(table)
    if header and len(table) == 1:
        header = False
    chosen = params.getlist("kolumna")
    valid = {key for key, _ in importing.FIELDS} | {""}
    if len(chosen) == width and all(key in valid for key in chosen):
        mapping = chosen
    else:
        mapping = importing.guess_mapping(table, header)
    return header, mapping


@login_required
@require_http_methods(["GET", "POST"])
def client_import_preview(request, import_id):
    draft = ClientImport.objects.filter(owner=request.user, pk=import_id).first()
    if draft is None:
        if request.method == "POST":
            # Imported already - a second click, or the back button.
            messages.info(request, "Ten plik został już zaimportowany albo wygasł.")
            return redirect("clients:list")
        raise Http404
    # Into the workspace the file was uploaded in - if the person may still
    # work there.
    target = draft.account or draft.owner
    if not team.can_work_in(request.user, target.pk):
        raise Http404
    params = request.POST if request.method == "POST" else request.GET
    header, mapping = _read_choices(params, draft)
    problem = importing.mapping_problem(mapping)
    rows = importing.check_rows(target, draft.table, header, mapping)
    update_existing = params.get("istniejacy") == "aktualizuj"

    if request.method == "POST" and problem is None:
        result = importing.run_import(
            target,
            rows,
            update_existing=update_existing,
            django_request=request,
        )
        draft.delete()
        messages.success(request, _result_message(result))
        return redirect("clients:list")

    table = draft.table
    examples = table[1:] if header else table
    columns = [
        {
            "index": index,
            "name": f"„{table[0][index]}”" if header and table[0][index] else "",
            "letter": _column_letter(index),
            "example": next((row[index] for row in examples if row[index]), ""),
            "field": mapping[index],
        }
        for index in range(len(table[0]))
    ]
    labels = importing.FIELD_LABELS
    counts = importing.summary(rows)
    new = counts[importing.NEW]
    existing = counts[importing.EXISTING]
    skipped = counts[importing.ERROR] + counts[importing.REPEATED]
    new_word = _plural(new, "klienta", "klientów", "klientów")
    existing_word = _plural(existing, "klienta", "klientów", "klientów")
    shown = [(key, label) for key, label in importing.FIELDS if key in mapping]
    sample = [row for row in rows if row.status == importing.NEW][:SAMPLE_ROWS]
    for row in sample:
        row.cells = [(label, row.values[key]) for key, label in shown]
    return render(
        request,
        "clients/import_preview.html",
        {
            "draft": draft,
            # Named when it isn't the workspace on screen now.
            "target_name": None
            if target.pk == request.account.pk
            else (
                "Moje konto" if target.pk == request.user.pk else team.firm_name(target)
            ),
            "header": header,
            "columns": columns,
            "fields": importing.FIELDS,
            # What goes where, in a line: "Nazwa „Nazwa kontrahenta”" - the
            # file's own header only when it says something else.
            "mapped": [
                (labels[key], _source(column, labels[key]))
                for key, _ in importing.FIELDS
                for column in columns
                if column["field"] == key
            ],
            "problem": problem,
            "new": new,
            "existing": existing,
            "skipped": skipped,
            "issues": [row for row in rows if row.notes],
            "sample": sample,
            "shown_labels": [label for _, label in shown],
            "update_existing": update_existing,
            "new_word": new_word,
            "skipped_word": _plural(skipped, "wiersz", "wiersze", "wierszy"),
            "add_label": f"Dodaj {new} {new_word}" if new else "Brak nowych klientów",
            "add_update_label": (
                f"Dodaj {new} i zaktualizuj {existing}"
                if new
                else f"Zaktualizuj {existing} {existing_word}"
            ),
        },
    )


def _source(column, label):
    if not column["name"]:
        return f"kolumna {column['letter']}"
    if column["name"].strip("„”").lower() == label.lower():
        return ""
    return column["name"]


def _plural(number, one, few, many):
    """1 wiersz, 2 wiersze, 5 wierszy, 22 wiersze."""
    if number == 1:
        return one
    if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14):
        return few
    return many


def _column_letter(index):
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def _result_message(result):
    parts = [f"Dodano klientów: {result['created']}."]
    if result["updated"]:
        parts.append(f"Zaktualizowano: {result['updated']}.")
    if result["skipped"]:
        parts.append(f"Pominięto wierszy: {result['skipped']}.")
    return " ".join(parts)


SAMPLE = (
    "Nazwa;E-mail;Telefon;NIP;Uwagi\r\n"
    "Kowalski Usługi Remontowe;biuro@kowalski-remonty.pl;600 100 200;;"
    "Ryczałt, dokumenty do 7. dnia miesiąca\r\n"
    "Anna Nowak;anna.nowak@example.com;;;Najem prywatny\r\n"
)


@login_required
def client_import_sample(request):
    """A file to fill in: the headers the import recognises, two examples.
    UTF-8 with a BOM and semicolons, so Excel in Poland opens it right."""
    response = HttpResponse("\ufeff" + SAMPLE, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        'attachment; filename="klienci-wzor-monituj-pl.csv"'
    )
    return response
