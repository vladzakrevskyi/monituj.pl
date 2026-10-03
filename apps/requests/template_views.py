"""The panel's "Szablony" page: own templates (list, new, edit, delete) and
the ready ones, plus "Zapisz jako szablon" on a sent request."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.common.exceptions import ApplicationError
from apps.common.forms import add_service_error
from apps.common.responses import (
    ajax_form_error_response,
    is_ajax_request,
    success_response,
)
from apps.requests import request_templates, template_library
from apps.requests.forms import RequestTemplateForm
from apps.requests.models import Request, RequestTemplate

FIELD_BY_CODE = {
    "TEMPLATE_TITLE": "title",
    "TEMPLATE_TITLE_TAKEN": "title",
    "TEMPLATE_ITEMS": "items",
    "TEMPLATE_DEADLINE": "deadline_days",
}


@login_required
def template_list(request):
    own = list(
        RequestTemplate.objects.filter(owner=request.account).order_by(
            "-last_used_at", "title"
        )
    )
    for template in own:
        template.deadline_text = request_templates.deadline_label(template)
    return render(
        request,
        "requests/templates.html",
        {
            "own": own,
            "usage": request_templates.usage(request.account),
            "ready_groups": request_templates.picker(request.account)["ready_groups"],
        },
    )


def _save(request, form, template=None):
    item_names = form.item_names()
    if not form.is_valid():
        return None
    data = form.cleaned_data
    try:
        return request_templates.save(
            request.account,
            title=data["title"],
            name=data["name"],
            description=data["description"],
            item_names=item_names,
            deadline_choice=data["deadline_choice"],
            deadline_days=data.get("deadline_days"),
            settings=form.request_settings(),
            template=template,
        )
    except ApplicationError as exc:
        add_service_error(form, exc, FIELD_BY_CODE)
        return None


def _saved(request, message):
    messages.success(request, message)
    url = reverse("requests:templates")
    if is_ajax_request(request):
        return success_response({"redirect_url": url})
    return redirect(url)


def _form_page(request, form, template, item_names):
    if request.method == "POST" and is_ajax_request(request):
        return ajax_form_error_response(form)
    return render(
        request,
        "requests/template_form.html",
        {"form": form, "template": template, "posted_items": item_names},
    )


@login_required
@require_http_methods(["GET", "POST"])
def template_create(request):
    usage = request_templates.usage(request.account)
    if usage["at_limit"] and request.method == "GET":
        try:
            request_templates.check_can_add(request.account)
        except ApplicationError as exc:
            messages.error(request, exc.message)
        return redirect("requests:templates")
    if request.method == "POST":
        form = RequestTemplateForm(request.POST)
        saved = _save(request, form)
        if saved is not None:
            return _saved(request, f"Zapisano szablon „{saved.title}”.")
        return _form_page(request, form, None, form.item_names())
    return _form_page(
        request, RequestTemplateForm(initial={"deadline_choice": "14"}), None, []
    )


@login_required
@require_http_methods(["GET", "POST"])
def template_edit(request, template_id):
    template = get_object_or_404(RequestTemplate, pk=template_id, owner=request.account)
    if request.method == "POST":
        form = RequestTemplateForm(request.POST)
        saved = _save(request, form, template)
        if saved is not None:
            return _saved(request, f"Zapisano zmiany w szablonie „{saved.title}”.")
        return _form_page(request, form, template, form.item_names())
    form = RequestTemplateForm(initial=RequestTemplateForm.initial_for(template))
    return _form_page(request, form, template, template.item_names)


@login_required
@require_POST
def template_delete(request, template_id):
    template = get_object_or_404(RequestTemplate, pk=template_id, owner=request.account)
    title = template.title
    template.delete()
    messages.success(request, f"Usunięto szablon „{title}”.")
    return redirect("requests:templates")


@login_required
@require_POST
def template_copy_ready(request, slug):
    ready = template_library.get(slug)
    if ready is None:
        raise Http404
    try:
        template = request_templates.copy_ready(request.account, ready)
    except ApplicationError as exc:
        messages.error(request, exc.message)
        return redirect("requests:templates")
    messages.success(
        request, f"Zapisano „{template.title}” jako Twój szablon - możesz go zmienić."
    )
    return redirect("requests:template-edit", template_id=template.pk)


@login_required
@require_POST
def template_from_request(request, request_id):
    request_obj = get_object_or_404(Request, pk=request_id, created_by=request.account)
    try:
        template = request_templates.from_request(request.account, request_obj)
    except ApplicationError as exc:
        messages.error(request, exc.message)
        return redirect("requests:detail", request_id=request_obj.pk)
    messages.success(
        request,
        f"Zapisano szablon „{template.title}”. Zmień nazwę albo listę, jeśli chcesz.",
    )
    return redirect("requests:template-edit", template_id=template.pk)
