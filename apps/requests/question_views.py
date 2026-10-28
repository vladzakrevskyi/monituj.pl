"""The panel's "Pytania": asking a client a question, the list of questions
with how long each has waited, and the sender's own note on any request
(apps/requests/questions.py)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.common.exceptions import ApplicationError
from apps.common.forms import add_service_error
from apps.requests import questions
from apps.requests.forms import PrivateNoteForm, QuestionForm
from apps.requests.models import RequestItemKind, RequestItemStatus
from apps.requests.services import RequestService

TABS = [
    (
        "czeka",
        "Czeka na odpowiedź",
        (RequestItemStatus.BRAK, RequestItemStatus.ODRZUCONY),
    ),
    ("odpowiedziano", "Do sprawdzenia", (RequestItemStatus.DOSTARCZONY,)),
    ("wyjasnione", "Wyjaśnione", (RequestItemStatus.ZAAKCEPTOWANY,)),
]


def _rows(owner):
    """Each question with its item and how many days it has waited."""
    today = timezone.localdate()
    rows = []
    for request_obj in questions.for_owner(owner):
        item = next(
            (i for i in request_obj.items.all() if i.kind == RequestItemKind.QUESTION),
            None,
        )
        if item is None:
            continue
        asked = timezone.localtime(request_obj.created_at).date()
        if item.answered_at and item.status != RequestItemStatus.ODRZUCONY:
            waited = (timezone.localtime(item.answered_at).date() - asked).days
        else:
            waited = (today - asked).days
        rows.append({"request": request_obj, "item": item, "waited": waited})
    return rows


@login_required
def question_list(request):
    rows = _rows(request.account)
    counts = {
        key: sum(1 for row in rows if row["item"].status in statuses)
        for key, _label, statuses in TABS
    }
    tab = request.GET.get("tab") or "czeka"
    statuses = dict((key, statuses) for key, _label, statuses in TABS).get(tab)
    shown = [row for row in rows if statuses is None or row["item"].status in statuses]
    if tab == "czeka":
        shown.sort(key=lambda row: -row["waited"])  # longest waiting first
    return render(
        request,
        "requests/questions.html",
        {
            "rows": shown,
            "tabs": [
                {"key": key, "label": label, "count": counts[key]}
                for key, label, _statuses in TABS
            ],
            "all_count": len(rows),
            "tab": tab if statuses is not None else "wszystkie",
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def question_create(request):
    if request.method == "POST":
        form = QuestionForm(request.POST, owner=request.account)
        if form.is_valid():
            data = form.cleaned_data
            try:
                request_obj = questions.ask(
                    owner=request.account,
                    client_id=data["client"].pk,
                    question=data["question"],
                    note=data["note"],
                    deadline=data["deadline"],
                    reminder_settings=form.reminder_settings(),
                    request=request,
                )
            except ApplicationError as exc:
                add_service_error(form, exc)
            else:
                messages.success(
                    request, f"Pytanie wysłane do klienta {data['client'].name}."
                )
                return redirect("requests:question-detail", request_obj.pk)
    else:
        client = request.GET.get("client", "")
        form = QuestionForm(
            owner=request.account,
            initial={"client": int(client)} if client.isdigit() else None,
        )
    previous = []
    chosen = form["client"].value()
    if chosen and str(chosen).isdigit():
        previous = [
            row
            for row in _rows(request.account)
            if row["request"].client_id == int(chosen)
        ][:5]
    return render(
        request,
        "requests/question_form.html",
        {"form": form, "previous": previous},
    )


@login_required
@require_POST
def request_note(request, request_id):
    """ "Notatka dla siebie" on any request."""
    try:
        request_obj = RequestService.get_owned_request(request.account, request_id)
    except ApplicationError:
        raise Http404 from None
    form = PrivateNoteForm(request.POST)
    if form.is_valid():
        questions.save_note(request_obj, form.cleaned_data["note"])
        messages.success(request, "Notatka zapisana.")
    else:
        messages.error(request, form.errors["note"][0])
    return redirect(request_obj.panel_url())
