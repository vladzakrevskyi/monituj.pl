from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models, transaction
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.formats import date_format
from django.views.decorators.http import require_http_methods

from apps.audit.models import AuditEvent
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
from apps.documents import archive
from apps.notifications import inbox
from apps.reminders.schedule import recipient_zone, send_clock
from apps.reminders.services import ReminderScheduleService
from apps.requests import received, recurring
from apps.requests.forms import (
    RecurringRequestForm,
    RequestEditForm,
    RequestFilterForm,
    RequestForm,
    reminder_preset_of,
)
from apps.requests.models import RecurringRequest, Request, RequestItem
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
    _attach_schedules(request.user, page_obj.object_list)

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
            # Not sent yet, so no row of their own - listed on top of the
            # first page, unless the list is narrowed down.
            "planned": (
                _planned(request.user)
                if page_obj.number == 1
                and not status_filter
                and not advanced_count
                and not request.GET.get("q")
                else []
            ),
        },
    )


def _described(schedule):
    schedule.next_name = recurring.render_name(schedule.name, schedule.next_run_on)
    schedule.when = recurring.describe(schedule)
    schedule.deadline_text = recurring.describe_deadline(schedule)
    return schedule


def _attach_schedules(owner, rows):
    """Each request sent by a recurring one gets it, to say so in its row."""
    ids = {row.recurring_id for row in rows if row.recurring_id}
    schedules = {
        schedule.pk: _described(schedule)
        for schedule in RecurringRequest.objects.filter(owner=owner, pk__in=ids)
    }
    for row in rows:
        row.schedule = schedules.get(row.recurring_id)


def _planned(owner):
    """Recurring requests that haven't sent anything yet."""
    schedules = (
        RecurringRequest.objects.filter(owner=owner, requests__isnull=True)
        .annotate(clients_count=models.Count("clients", distinct=True))
        .order_by("-active", "next_run_on", "id")
    )
    return [_described(schedule) for schedule in schedules]


@login_required
@require_http_methods(["GET", "POST"])
def request_create(request):
    item_names = []
    if request.method == "POST":
        form = RequestForm(request.POST, owner=request.user)
        item_names = form.item_names()
        if form.is_valid() and form.is_recurring:
            try:
                form.save_sender_name(request.user)
                return _save_recurring(request, form, item_names)
            except ApplicationError as exc:
                add_service_error(form, exc)
        elif form.is_valid() and form.to_many:
            try:
                form.save_sender_name(request.user)
                sent = RequestService.create_many(
                    owner=request.user,
                    client_ids=form.cleaned_data["client_ids"],
                    name=form.cleaned_data["name"],
                    description=form.cleaned_data["description"],
                    deadline=form.cleaned_data["deadline"],
                    item_names=item_names,
                    reminder_settings=form.request_settings(),
                    request=request,
                    new_clients=form.cleaned_data["new_clients_list"],
                )
                messages.success(
                    request,
                    f"Prośba „{form.cleaned_data['name']}” wysłana do "
                    f"{clients_phrase(len(sent))} – wiadomości dotrą w ciągu minuty.",
                )
                redirect_url = reverse("requests:list")
                if is_ajax_request(request):
                    return success_response({"redirect_url": redirect_url})
                return redirect(redirect_url)
            except ApplicationError as exc:
                add_service_error(form, exc)
        elif form.is_valid():
            try:
                form.save_sender_name(request.user)
                if form.cleaned_data["client_ids"]:
                    client_id = form.cleaned_data["client_ids"][0]
                else:
                    new_name, new_email = form.cleaned_data["new_clients_list"][0]
                    new_client = ClientService.get_or_create_by_email(
                        owner=request.user,
                        email=new_email,
                        name=new_name,
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
        form = RequestForm(owner=request.user, initial=_last_used(request.user))
    preselected = request.GET.get("client", "")
    return render(
        request,
        "requests/form.html",
        {
            "form": form,
            "mode": "create",
            "posted_items": item_names,
            "schedule": "recurring" if form.is_bound and form.is_recurring else "once",
            "suggested_items": suggested_items(request.user),
            "client_options": [
                {"id": c.pk, "name": c.name, "email": c.email}
                for c in form.fields["clients"].queryset
            ],
            "preselected": int(preselected) if preselected.isdigit() else None,
        },
    )


# What accounting offices ask for most - after the owner's own habits.
COMMON_ITEMS = [
    "Faktury sprzedaży",
    "Faktury kosztowe",
    "Wyciąg bankowy",
    "Paragony",
    "Umowy",
    "Lista płac",
    "Dokumenty kadrowe",
    "Raport kasowy",
]
SUGGESTED_ITEMS = 8


def suggested_items(owner):
    """Documents to add with a click: the ones this owner asks for most,
    then the usual ones."""
    own = (
        RequestItem.objects.filter(request__created_by=owner)
        .values("name")
        .annotate(uses=models.Count("id"))
        .order_by("-uses", "name")
        .values_list("name", flat=True)[:SUGGESTED_ITEMS]
    )
    seen, names = set(), []
    for name in [*own, *COMMON_ITEMS]:
        if name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return names[:SUGGESTED_ITEMS]


def _last_used(owner):
    """The form starts with the reminders and file keeping of the owner's
    last request - set once, not every time."""
    last = Request.objects.filter(created_by=owner).order_by("-created_at").first()
    if last is None:
        return {"deadline_choice": "14", "reminder_preset": "standard"}
    return {
        "deadline_choice": "14",
        "reminder_preset": reminder_preset_of(
            last.reminders_enabled,
            last.first_reminder_after_days,
            last.reminder_frequency_days,
            last.max_reminders,
        ),
        "first_reminder_after_days": last.first_reminder_after_days,
        "reminder_frequency_days": last.reminder_frequency_days,
        "max_reminders": last.max_reminders,
        **RequestForm.retention_initial(last.retention_days),
    }


def _save_recurring(request, form, item_names):
    data = form.cleaned_data
    client_ids, new_clients = data["client_ids"], data["new_clients_list"]
    schedule, sent = recurring.create(
        owner=request.user,
        client_ids=client_ids,
        new_clients=new_clients,
        name=data["name"],
        description=data["description"],
        item_names=item_names,
        timing=form.timing(),
        deadline_days=data.get("deadline_days"),
        deadline_month_day=data.get("deadline_month_day"),
        settings=form.request_settings(),
        send_now=bool(data.get("send_first_now")),
        request=request,
    )
    message = (
        f"Prośba cykliczna zapisana ({recurring.describe(schedule)}). Najbliższe "
        "wysyłki: "
        + ", ".join(date_format(day, "j E") for day in recurring.upcoming(schedule))
        + "."
    )
    if sent:
        message += f" Pierwsze prośby wysłane do {clients_phrase(len(sent))}."
    messages.success(request, message)
    redirect_url = reverse("requests:list")
    if is_ajax_request(request):
        return success_response({"redirect_url": redirect_url})
    return redirect(redirect_url)


def clients_phrase(count):
    """1 klienta, 2 klientów, 5 klientów - genitive, after "do"."""
    return f"{count} klienta" if count == 1 else f"{count} klientów"


@login_required
def request_detail(request, request_id):
    try:
        request_obj = RequestService.get_owned_request(request.user, request_id)
    except ApplicationError:
        raise Http404 from None

    # Whoever opens the request has seen what arrived.
    inbox.mark_read(request.user, request_obj)
    items = request_obj.items.all().order_by("id")
    reminders = request_obj.reminders.all().order_by("-sent_at")
    history = AuditService.history_for_request(request_obj)
    for entry in history:
        entry.label_pl = translate_event(entry.event)
        by = (entry.metadata or {}).get("by")
        if by:
            entry.label_pl += " (Ty)" if by == "owner" else " (odbiorca)"
        if (entry.metadata or {}).get("zip"):
            entry.label_pl += " – w archiwum ZIP"
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
            "has_files": archive.documents_of(request_obj).exists(),
            "schedule": _schedule_of(request_obj),
        },
    )


@login_required
@require_http_methods(["GET"])
def request_files_zip(request, request_id):
    """Every file of the request in one ZIP, in folders by document."""
    try:
        request_obj = RequestService.get_owned_request(request.user, request_id)
    except ApplicationError:
        raise Http404 from None
    zipped, documents = archive.build(request_obj)
    if not documents:
        zipped.close()
        messages.error(request, "W tej prośbie nie ma jeszcze plików do pobrania.")
        return redirect("requests:detail", request_id=request_obj.pk)
    for document in documents:
        AuditService.log(
            AuditEvent.FILE_DOWNLOAD,
            actor=request.user,
            target=document,
            request=request,
            metadata={"by": "owner", "zip": True},
        )
    response = FileResponse(
        zipped, as_attachment=True, filename=archive.archive_name(request_obj)
    )
    response["Content-Type"] = "application/zip"
    return response


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
        try:
            RequestService.reopen(request_obj, actor=request.user, request=request)
        except ApplicationError as exc:
            messages.error(request, exc.message)
        else:
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


# --- Recurring requests -------------------------------------------------------


def _own_schedule(request, schedule_id):
    schedule = (
        RecurringRequest.objects.filter(owner=request.user, pk=schedule_id)
        .select_related("owner")
        .first()
    )
    if schedule is None:
        raise Http404
    return schedule


@login_required
@require_http_methods(["POST"])
def recurring_send_now(request, schedule_id):
    schedule = _own_schedule(request, schedule_id)
    today = recurring.owner_now(request.user).date()
    try:
        with transaction.atomic():
            sent = recurring.run(schedule, today, request=request, extra=True)
    except ApplicationError as exc:
        messages.error(request, exc.message)
    else:
        next_run = (
            f"Harmonogram bez zmian – następna wysyłka "
            f"{date_format(schedule.next_run_on, 'j E Y')}."
            if schedule.active
            else "Harmonogram pozostaje wstrzymany."
        )
        messages.success(
            request,
            f"Wysłano „{recurring.render_name(schedule.name, today)}” do "
            f"{clients_phrase(len(sent))}. {next_run}",
        )
    return redirect("requests:recurring-edit", schedule.pk)


@login_required
@require_http_methods(["POST"])
def recurring_toggle(request, schedule_id):
    schedule = _own_schedule(request, schedule_id)
    schedule.active = not schedule.active
    if schedule.active:
        # Resumed after its day passed: the next one ahead, no catching up.
        today = recurring.owner_now(request.user).date()
        if schedule.next_run_on < today:
            recurring.reschedule(schedule, today)
    schedule.save()
    messages.success(
        request,
        "Prośba cykliczna wznowiona."
        if schedule.active
        else "Prośba cykliczna wstrzymana.",
    )
    return redirect("requests:recurring-edit", schedule.pk)


@login_required
@require_http_methods(["POST"])
def recurring_delete(request, schedule_id):
    schedule = _own_schedule(request, schedule_id)
    schedule.delete()
    messages.success(
        request,
        "Prośba cykliczna usunięta. Prośby już wysłane zostają na liście.",
    )
    return redirect("requests:list")


@login_required
@require_http_methods(["GET", "POST"])
def recurring_edit(request, schedule_id):
    schedule = _own_schedule(request, schedule_id)
    item_names = list(schedule.item_names)
    if request.method == "POST":
        form = RecurringRequestForm(request.POST, owner=request.user)
        item_names = form.item_names()
        if form.is_valid():
            data = form.cleaned_data
            timing = form.timing()
            timing_changed = any(
                getattr(schedule, field) != value for field, value in timing.items()
            )
            schedule.name = data["name"]
            schedule.description = data["description"]
            schedule.item_names = item_names
            schedule.deadline_days = data.get("deadline_days")
            if schedule.deadline_days:
                schedule.deadline_month_day = None
            for field, value in {**timing, **form.request_settings()}.items():
                setattr(schedule, field, value)
            if timing_changed:
                recurring.reschedule(schedule, recurring.owner_now(request.user).date())
            schedule.save()
            schedule.clients.set(data["clients"])
            messages.success(
                request,
                "Prośba cykliczna zapisana. Najbliższe wysyłki: "
                + ", ".join(
                    date_format(day, "j E") for day in recurring.upcoming(schedule)
                )
                + ".",
            )
            redirect_url = reverse("requests:list")
            if is_ajax_request(request):
                return success_response({"redirect_url": redirect_url})
            return redirect(redirect_url)
        if is_ajax_request(request):
            return ajax_form_error_response(form)
    else:
        form = RecurringRequestForm(
            owner=request.user,
            initial={
                "name": schedule.name,
                "description": schedule.description,
                "clients": list(schedule.clients.values_list("pk", flat=True)),
                "interval": schedule.interval,
                "month_day": schedule.month_day or 1,
                "weekday": schedule.weekday if schedule.weekday is not None else 0,
                "workdays_only": schedule.workdays_only,
                "deadline_days": schedule.deadline_days,
                "reminders_enabled": schedule.reminders_enabled,
                "first_reminder_after_days": schedule.first_reminder_after_days,
                "reminder_frequency_days": schedule.reminder_frequency_days,
                "max_reminders": schedule.max_reminders,
                **RecurringRequestForm.retention_initial(schedule.retention_days),
            },
        )
    return render(
        request,
        "requests/recurring_form.html",
        {
            "form": form,
            "schedule": _described(schedule),
            # What "send now" sends: named after today, not the next run.
            "now_name": recurring.render_name(
                schedule.name, recurring.owner_now(request.user).date()
            ),
            "clients_count": schedule.clients.count(),
            "sent_count": schedule.requests.count(),
            "posted_items": item_names,
            "selected": {
                int(pk) for pk in (form["clients"].value() or []) if str(pk).isdigit()
            },
        },
    )


def _schedule_of(request_obj):
    schedule = request_obj.recurring
    if schedule is None:
        return None
    schedule.when = recurring.describe(schedule)
    return schedule
