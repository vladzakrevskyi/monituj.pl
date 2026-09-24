from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.audit.services import AuditService, translate_event
from apps.clients.services import ClientService
from apps.common.exceptions import ApplicationError
from apps.common.filters import active_filter_count, query_without_page, status_tabs
from apps.common.forms import add_service_error
from apps.common.responses import (
    ajax_form_error_response,
    is_ajax_request,
    success_response,
)
from apps.reminders.schedule import recipient_zone, send_clock
from apps.reminders.services import ReminderScheduleService
from apps.requests import received
from apps.requests.forms import RequestEditForm, RequestFilterForm, RequestForm
from apps.requests.services import RequestService, compute_status


@login_required
def request_list(request):
    filters = RequestFilterForm(request.GET, owner=request.user)
    client = filters.value("client")
    results = RequestService.filter_for_owner(
        request.user,
        search=(filters.value("q") or "").strip(),
        client_id=client.pk if client else None,
        deadline_from=filters.value("deadline_from"),
        deadline_to=filters.value("deadline_to"),
        reminders=filters.value("reminders"),
        sort=filters.value("sort") or "newest",
    )

    status_filter = filters.value("status") or ""
    tabs = status_tabs(
        request, RequestFilterForm.STATUS_CHOICES, results, status_filter
    )
    if status_filter:
        results = [r for r in results if r.status_code == status_filter]
    page_obj = Paginator(results, 20).get_page(request.GET.get("page", 1))
    for request_obj in page_obj.object_list:
        status = compute_status(request_obj)
        request_obj.status_label = status.label
        request_obj.status_code = status.value

    advanced_count = active_filter_count(
        request,
        ("client", "deadline_from", "deadline_to", "reminders", "sort"),
        defaults={"sort": "newest"},
    )
    return render(
        request,
        "requests/list.html",
        {
            "page_obj": page_obj,
            "filters": filters,
            "status_tabs": tabs,
            "page_query": query_without_page(request),
            "has_filters": bool(request.GET.get("q") or advanced_count),
            "advanced_count": advanced_count,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def request_create(request):
    item_names = []
    if request.method == "POST":
        form = RequestForm(request.POST, owner=request.user)
        item_names = form.item_names()
        if form.is_valid():
            try:
                if form.cleaned_data.get("client"):
                    client_id = form.cleaned_data["client"].pk
                else:
                    new_client = ClientService.get_or_create_by_email(
                        owner=request.user,
                        email=form.cleaned_data["new_client_email"],
                        name=form.cleaned_data.get("new_client_name", ""),
                        request=request,
                    )
                    client_id = new_client.pk
                request_obj = RequestService.create(
                    owner=request.user,
                    client_id=client_id,
                    name=form.cleaned_data["name"],
                    description=form.cleaned_data["description"],
                    deadline=form.cleaned_data["deadline"],
                    item_names=item_names,
                    password=form.cleaned_data["password"],
                    reminder_settings=form.request_settings(),
                    request=request,
                )
                messages.success(request, "Przypomnienie zostało utworzone.")
                redirect_url = reverse("requests:detail", args=[request_obj.pk])
                if is_ajax_request(request):
                    return success_response({"redirect_url": redirect_url})
                return redirect(redirect_url)
            except ApplicationError as exc:
                add_service_error(form, exc)
        if is_ajax_request(request):
            return ajax_form_error_response(form)
    else:
        preselected = request.GET.get("client", "")
        form = RequestForm(
            owner=request.user,
            initial={"client": preselected} if preselected.isdigit() else None,
        )
    return render(
        request,
        "requests/form.html",
        {"form": form, "mode": "create", "posted_items": item_names},
    )


@login_required
def request_detail(request, request_id):
    try:
        request_obj = RequestService.get_owned_request(request.user, request_id)
    except ApplicationError:
        raise Http404 from None

    items = request_obj.items.all().order_by("id")
    reminders = request_obj.reminders.all().order_by("-sent_at")
    history = AuditService.history_for_request(request_obj)
    for entry in history:
        entry.label_pl = translate_event(entry.event)
    status = compute_status(request_obj)
    return render(
        request,
        "requests/detail.html",
        {
            "request_obj": request_obj,
            "items": items,
            "reminders": reminders,
            "history": history,
            "status_label": status.label,
            "status_code": status.value,
            "public_url": request.build_absolute_uri(f"/d/{request_obj.public_token}/"),
            "planned_reminders": ReminderScheduleService.planned(request_obj),
            "reminder_clock": send_clock(request_obj),
            "recipient_timezone": recipient_zone(request_obj).key,
            "automatic_sent": sum(1 for r in reminders if r.kind == "automatic"),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def request_edit(request, request_id):
    try:
        request_obj = RequestService.get_owned_request(request.user, request_id)
    except ApplicationError:
        raise Http404 from None

    if request.method == "POST":
        form = RequestEditForm(request.POST)
        if form.is_valid():
            RequestService.update(
                request_obj,
                name=form.cleaned_data["name"],
                description=form.cleaned_data["description"],
                deadline=form.cleaned_data["deadline"],
                reminder_settings=form.request_settings(),
                request=request,
            )
            messages.success(request, "Zmiany zostały zapisane.")
            redirect_url = reverse("requests:detail", args=[request_obj.pk])
            if is_ajax_request(request):
                return success_response({"redirect_url": redirect_url})
            return redirect(redirect_url)
        if is_ajax_request(request):
            return ajax_form_error_response(form)
    else:
        form = RequestEditForm(
            initial={
                "name": request_obj.name,
                "description": request_obj.description,
                "deadline": request_obj.deadline.date()
                if request_obj.deadline
                else None,
                "reminders_enabled": request_obj.reminders_enabled,
                "first_reminder_after_days": request_obj.first_reminder_after_days,
                "reminder_frequency_days": request_obj.reminder_frequency_days,
                "max_reminders": request_obj.max_reminders,
                **RequestEditForm.retention_initial(request_obj.retention_days),
            }
        )
    return render(
        request,
        "requests/edit_form.html",
        {"form": form, "request_obj": request_obj},
    )


@login_required
@require_http_methods(["POST"])
def request_close(request, request_id):
    try:
        request_obj = RequestService.get_owned_request(request.user, request_id)
    except ApplicationError:
        raise Http404 from None
    if request.POST.get("action") == "reopen":
        RequestService.reopen(request_obj, actor=request.user, request=request)
        messages.success(
            request, "Prośba jest znowu otwarta – odbiorca może przesyłać pliki."
        )
    else:
        RequestService.close(request_obj, actor=request.user, request=request)
        messages.success(
            request,
            "Prośba została zamknięta. Przypomnienia nie będą wysyłane, a odbiorca "
            "nie może już przesyłać plików.",
        )
    return redirect("requests:detail", request_id=request_obj.pk)


@login_required
def received_list(request):
    """Requests other people sent to this account's (verified) address."""
    email = received.account_email(request.user)
    rows, tabs = received.filtered(
        received.received_requests(email) if email else [], request.GET.get("widok")
    )
    return render(
        request,
        "requests/received.html",
        {
            "rows": rows,
            "tabs": tabs,
            "active_view": next(t["key"] for t in tabs if t["active"]),
            "email_verified": bool(email),
        },
    )
