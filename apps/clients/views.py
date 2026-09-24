from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.clients.forms import ClientFilterForm, ClientForm
from apps.clients.services import ClientService
from apps.common.exceptions import ApplicationError
from apps.common.filters import active_filter_count, query_without_page, status_tabs
from apps.common.responses import (
    ajax_form_error_response,
    is_ajax_request,
    success_response,
)


@login_required
def client_list(request):
    filters = ClientFilterForm(request.GET)
    results = ClientService.filter_for_owner(
        request.user,
        search=(filters.value("q") or "").strip(),
        missing=filters.value("missing"),
        activity_from=filters.value("activity_from"),
        activity_to=filters.value("activity_to"),
        sort=filters.value("sort") or "name",
    )
    status_filter = filters.value("status") or ""
    tabs = status_tabs(request, ClientFilterForm.STATUS_CHOICES, results, status_filter)
    if status_filter:
        results = [c for c in results if c.status_code == status_filter]
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
            "page_query": query_without_page(request),
            "has_filters": bool(request.GET.get("q") or advanced_count),
            "advanced_count": advanced_count,
            "create_form": ClientForm(auto_id="id_create_%s"),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def client_create(request):
    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            ClientService.create(
                owner=request.user,
                name=form.cleaned_data["name"],
                email=form.cleaned_data["email"],
                phone=form.cleaned_data["phone"],
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
        client = ClientService.get_owned_client(request.user, client_id)
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
        client = ClientService.get_owned_client(request.user, client_id)
    except ApplicationError:
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
