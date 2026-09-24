from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.services import GuestOwnerService
from apps.clients.services import ClientService
from apps.common.exceptions import ApplicationError
from apps.common.forms import add_service_error
from apps.common.responses import (
    ajax_form_error_response,
    is_ajax_request,
    success_response,
)
from apps.documents.services import GuestUploadContext
from apps.requests.forms import PublicPasswordForm, PublicRequestForm
from apps.requests.services import PublicAccessService, RequestService, compute_status


@require_http_methods(["GET", "POST"])
def public_request_detail(request, token):
    try:
        request_obj = PublicAccessService.get_by_token(token)
    except ApplicationError:
        raise Http404 from None

    if request_obj.is_password_protected and not PublicAccessService.has_access(
        request_obj, request
    ):
        if request.method == "POST":
            form = PublicPasswordForm(request.POST)
            if form.is_valid():
                if PublicAccessService.check_password(
                    request_obj, form.cleaned_data["password"], request
                ):
                    redirect_url = reverse("public:request-detail", args=[token])
                    if is_ajax_request(request):
                        return success_response({"redirect_url": redirect_url})
                    return redirect(redirect_url)
                form.add_error("password", "Nieprawidłowe hasło.")
            if is_ajax_request(request):
                return ajax_form_error_response(form)
        else:
            form = PublicPasswordForm()
        return render(request, "public/password_gate.html", {"form": form})

    PublicAccessService.grant_access(request_obj, request)
    PublicAccessService.mark_accessed(request_obj, request)
    items = request_obj.items.all().order_by("id")
    own_docs = GuestUploadContext.own_documents_by_item(
        request_obj, request.session.session_key or ""
    )
    for item in items:
        item.own_documents = own_docs.get(item.id, [])

    status = compute_status(request_obj)
    return render(
        request,
        "public/request_detail.html",
        {
            "request_obj": request_obj,
            "items": items,
            "status_label": status.label,
            "status_code": status.value,
            "public_token": request_obj.public_token,
        },
    )


@require_http_methods(["GET", "POST"])
def guest_request_create(request):
    item_names = []
    if request.method == "POST":
        form = PublicRequestForm(request.POST)
        item_names = form.item_names()
        if form.is_valid():
            try:
                owner = GuestOwnerService.get_or_create()
                client = ClientService.get_or_create_by_email(
                    owner=owner,
                    email=form.cleaned_data["client_email"],
                    name=form.cleaned_data["client_name"],
                    request=request,
                )
                request_obj = RequestService.create_public(
                    owner=owner,
                    client_id=client.pk,
                    name=form.cleaned_data["name"],
                    description=form.cleaned_data["description"],
                    deadline=form.cleaned_data["deadline"],
                    item_names=item_names,
                    password=form.cleaned_data["password"],
                    reminder_settings=form.request_settings(),
                    django_request=request,
                )
                redirect_url = reverse(
                    "public:guest-request-created", args=[request_obj.public_token]
                )
                if is_ajax_request(request):
                    return success_response({"redirect_url": redirect_url})
                return redirect(redirect_url)
            except ApplicationError as exc:
                add_service_error(form, exc)
        if is_ajax_request(request):
            return ajax_form_error_response(form)
    else:
        form = PublicRequestForm()
    return render(
        request,
        "public/guest_request_form.html",
        {"form": form, "posted_items": item_names},
    )


def guest_request_created(request, token):
    try:
        request_obj = PublicAccessService.get_by_token(token)
    except ApplicationError:
        raise Http404 from None
    return render(
        request,
        "public/guest_request_created.html",
        {
            "request_obj": request_obj,
            "public_url": request.build_absolute_uri(f"/d/{token}/"),
        },
    )
