from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.services import GuestAccessService
from apps.common.exceptions import ApplicationError
from apps.common.forms import add_service_error
from apps.common.responses import (
    ajax_form_error_response,
    is_ajax_request,
    success_response,
)
from apps.documents.services import GuestUploadContext
from apps.requests.forms import PublicPasswordForm, PublicRequestForm
from apps.requests.guest import GuestRequestService
from apps.requests.models import RecipientAccess, Request
from apps.requests.services import PublicAccessService, compute_status, with_stats


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


SENDER_SESSION_KEY = "guest_request_sender"


@require_http_methods(["GET", "POST"])
def guest_request_create(request):
    if request.user.is_authenticated:
        # With an account (also one without a password) requests are sent
        # from the panel, straight away and without email confirmation.
        return redirect("requests:create")
    item_names = []
    if request.method == "POST":
        form = PublicRequestForm(request.POST)
        item_names = form.item_names()
        if form.is_valid():
            try:
                GuestRequestService.submit(form, request)
                request.session[SENDER_SESSION_KEY] = form.cleaned_data["sender_email"]
                redirect_url = reverse("public:guest-request-sent")
                if is_ajax_request(request):
                    return success_response({"redirect_url": redirect_url})
                return redirect(redirect_url)
            except ApplicationError as exc:
                add_service_error(
                    form,
                    exc,
                    {
                        "SENDER_UNAVAILABLE": "sender_email",
                        "GUEST_DAILY_LIMIT_REACHED": "sender_email",
                    },
                )
        if is_ajax_request(request):
            return ajax_form_error_response(form)
    else:
        form = PublicRequestForm()
    return render(
        request,
        "public/guest_request_form.html",
        {"form": form, "posted_items": item_names},
    )


def guest_request_sent(request):
    return render(
        request,
        "public/guest_request_sent.html",
        {"sender_email": request.session.get(SENDER_SESSION_KEY, "")},
    )


@require_http_methods(["GET", "POST"])
def guest_request_confirm(request, token):
    """GET only shows what is about to be sent; sending needs the button,
    so mail scanners that open links can't confirm on the sender's behalf."""
    try:
        if request.method == "GET":
            request_obj = GuestRequestService.pending(token)
            return render(
                request,
                "public/guest_request_confirm.html",
                {
                    "request_obj": request_obj,
                    "items": request_obj.items.order_by("id"),
                },
            )
        request_obj = GuestRequestService.confirm(token, django_request=request)
    except ApplicationError as exc:
        return render(
            request,
            "base/message.html",
            {"title": "Link nie działa", "message": exc.message},
            status=404,
        )

    owner = request_obj.created_by
    detail_url = reverse("requests:detail", args=[request_obj.pk])
    sent_message = f"Prośba została wysłana do {request_obj.client.email}."
    if hasattr(owner, "guest_access"):
        GuestAccessService.login(request, owner)
    if request.user == owner:
        messages.success(
            request,
            sent_message
            + (
                " Stały link do tego panelu wysłaliśmy Ci mailem."
                if hasattr(owner, "guest_access")
                else ""
            ),
        )
        return redirect(detail_url)
    return render(
        request,
        "base/message.html",
        {
            "title": "Prośba wysłana",
            "message": sent_message
            + " Zaloguj się na swoje konto, aby śledzić, które dokumenty już dotarły.",
        },
    )


def recipient_portal(request, token):
    access = RecipientAccess.objects.filter(token=token).first()
    if access is None:
        raise Http404
    requests = list(
        with_stats(
            Request.objects.filter(
                client__email__iexact=access.email, awaiting_confirmation=False
            ).select_related("created_by")
        ).order_by("closed_at", "-created_at")
    )
    for request_obj in requests:
        status = compute_status(request_obj)
        request_obj.status_label = status.label
        request_obj.status_code = status.value
    return render(
        request,
        "public/recipient_portal.html",
        {"recipient_email": access.email, "requests": requests},
    )
