from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.accounts import team
from apps.clients.forms import ClientFilterForm, ClientForm
from apps.clients.models import Client
from apps.clients.services import ClientService
from apps.common.exceptions import ApplicationError
from apps.common.filters import active_filter_count, status_tabs
from apps.common.responses import (
    ajax_form_error_response,
    is_ajax_request,
    success_response,
)

# The filter fields a bulk action carries along, to find "all" again.
FILTER_FIELDS = ("q", "status", "missing", "activity_from", "activity_to", "sort")


def _filtered(owner, params):
    """The owner's clients as the list shows them with these filters - also
    for "delete all on every page". -> (filters, all matching before the
    status tab, the status tab, the rows shown)."""
    filters = ClientFilterForm(params)
    everything = ClientService.filter_for_owner(
        owner,
        search=(filters.value("q") or "").strip(),
        missing=filters.value("missing"),
        activity_from=filters.value("activity_from"),
        activity_to=filters.value("activity_to"),
        sort=filters.value("sort") or "name",
    )
    status_filter = filters.value("status") or ""
    results = everything
    if status_filter:
        results = [c for c in everything if c.status_code == status_filter]
    return filters, everything, status_filter, results


@login_required
def client_list(request):
    filters, everything, status_filter, results = _filtered(
        request.account, request.GET
    )
    tabs = status_tabs(
        request, ClientFilterForm.STATUS_CHOICES, everything, status_filter
    )
    page_obj = Paginator(results, 20).get_page(request.GET.get("page", 1))

    advanced_count = active_filter_count(
        request,
        ("missing", "activity_from", "activity_to", "sort"),
        defaults={"sort": "name"},
    )
    return render(
        request,
        "clients/list.html",
        {
            "page_obj": page_obj,
            "filters": filters,
            "status_tabs": tabs,
            "has_filters": bool(request.GET.get("q") or advanced_count),
            "advanced_count": advanced_count,
            "create_form": ClientForm(auto_id="id_create_%s"),
            "filter_params": [
                (key, value)
                for key in FILTER_FIELDS
                for value in request.GET.getlist(key)
                if value
            ],
        },
    )


@login_required
@require_http_methods(["POST"])
def client_bulk_delete(request):
    """The list's "Usuń zaznaczonych": the ticked clients, or with all=1
    every client matching the filters sent along. A client with requests
    goes with all of them, their files and history (apps/requests/deletion)."""
    from apps.requests import deletion

    if not team.is_owner(request):
        messages.error(request, team.OWNER_ONLY_MESSAGE)
        return redirect("clients:list")
    if request.POST.get("all") == "1":
        ids = [c.pk for c in _filtered(request.account, request.POST)[3]]
    else:
        ids = [int(i) for i in request.POST.getlist("ids") if i.isdigit()]
    query = urlencode(
        [
            (key, value)
            for key in FILTER_FIELDS
            for value in request.POST.getlist(key)
            if value
        ]
    )
    back = reverse("clients:list") + (f"?{query}" if query else "")
    clients = list(Client.objects.filter(owner=request.account, pk__in=ids))
    if not clients:
        messages.info(request, "Nie zaznaczono żadnego klienta.")
        return redirect(back)
    removed = {"requests": 0, "files": 0}
    for client in clients:
        gone = deletion.delete_client_with_history(client, django_request=request)
        removed["requests"] += gone["requests"]
        removed["files"] += gone["files"]
    message = f"Usunięto klientów: {len(clients)}."
    if removed["requests"]:
        message += f" Razem z nimi prośby: {removed['requests']}"
        if removed["files"]:
            message += f" i przesłane pliki: {removed['files']}"
        message += "."
    messages.success(request, message)
    return redirect(back)


@login_required
@require_http_methods(["GET", "POST"])
def client_create(request):
    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            ClientService.create(
                owner=request.account,
                name=form.cleaned_data["name"],
                email=form.cleaned_data["email"],
                phone=form.cleaned_data["phone"],
                nip=form.cleaned_data["nip"],
                note=form.cleaned_data["note"],
                request=request,
            )
            messages.success(request, "Klient został dodany.")
            redirect_url = reverse("clients:list")
            if is_ajax_request(request):
                return success_response({"redirect_url": redirect_url})
            return redirect(redirect_url)
        if is_ajax_request(request):
            return ajax_form_error_response(form)
    else:
        form = ClientForm()
    return render(request, "clients/form.html", {"form": form, "mode": "create"})


@login_required
@require_http_methods(["GET", "POST"])
def client_edit(request, client_id):
    try:
        client = ClientService.get_owned_client(request.account, client_id)
    except ApplicationError:
        raise Http404 from None

    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            ClientService.update(
                client,
                name=form.cleaned_data["name"],
                email=form.cleaned_data["email"],
                phone=form.cleaned_data["phone"],
                nip=form.cleaned_data["nip"],
                note=form.cleaned_data["note"],
                request=request,
            )
            messages.success(request, "Zmiany zostały zapisane.")
            redirect_url = reverse("clients:list")
            if is_ajax_request(request):
                return success_response({"redirect_url": redirect_url})
            return redirect(redirect_url)
        if is_ajax_request(request):
            return ajax_form_error_response(form)
    else:
        form = ClientForm(
            initial={
                "name": client.name,
                "email": client.email,
                "phone": client.phone,
                "nip": client.nip,
                "note": client.note,
            }
        )
    return render(
        request, "clients/form.html", {"form": form, "mode": "edit", "client": client}
    )


CLIENT_DOCUMENT_TABS = [
    ("all", "Wszystkie"),
    ("brakujace", "Brakujące"),
    ("dostarczone", "Dostarczone"),
]


@login_required
def client_documents(request, client_id):
    try:
        client = ClientService.get_owned_client(request.account, client_id)
    except ApplicationError:
        # A link to another of the user's workspaces.
        found = Client.objects.filter(pk=client_id).select_related("owner").first()
        if found is not None and team.follow(request, found.owner):
            return redirect(request.get_full_path())
        raise Http404 from None

    status_filter = request.GET.get("status", "all")
    if status_filter not in dict(CLIENT_DOCUMENT_TABS):
        status_filter = "all"
    counts = ClientService.document_counts(client)
    tabs = [
        {
            "code": code,
            "label": label,
            "count": counts[code],
            "active": code == status_filter,
        }
        for code, label in CLIENT_DOCUMENT_TABS
    ]
    items = ClientService.documents(client, status_filter)
    page_obj = Paginator(items, 25).get_page(request.GET.get("page", 1))
    return render(
        request,
        "clients/documents.html",
        {
            "client": client,
            "page_obj": page_obj,
            "tabs": tabs,
            "status_filter": status_filter,
        },
    )
