from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.models import User
from apps.accounts.services import GuestAccessService
from apps.common.exceptions import ApplicationError
from apps.common.forms import add_service_error
from apps.common.responses import (
    ajax_form_error_response,
    is_ajax_request,
    success_response,
)
from apps.documents.services import GuestUploadContext
from apps.requests import received
from apps.requests.forms import PublicPasswordForm, PublicRequestForm
from apps.requests.guest import GuestRequestService
from apps.requests.links import remember_recipient_timezone
from apps.requests.models import RecipientAccess
from apps.requests.services import PublicAccessService, compute_status


@require_http_methods(["GET", "POST"])
def public_request_detail(request, token):
    try:
        request_obj = PublicAccessService.get_by_token(token)
    except ApplicationError:
        raise Http404 from None

    # The recipient signed in to their own account already proved they own
    # the address the password was mailed to.
    verified = received.is_verified_recipient(request, request_obj.client.email)
    if (
        request_obj.is_password_protected
        and not verified
        and not PublicAccessService.has_access(request_obj, request)
    ):
        if request.method == "POST":
            form = PublicPasswordForm(request.POST)
            if form.is_valid():
                try:
                    correct = PublicAccessService.check_password(
                        request_obj, form.cleaned_data["password"], request
                    )
                except ApplicationError as exc:
                    form.add_error("password", exc.message)
                    correct = None
                if correct:
                    redirect_url = reverse("public:request-detail", args=[token])
                    if is_ajax_request(request):
                        return success_response({"redirect_url": redirect_url})
                    return redirect(redirect_url)
                if correct is False:
                    form.add_error("password", "Nieprawidłowe hasło.")
            if is_ajax_request(request):
                return ajax_form_error_response(form)
        else:
            form = PublicPasswordForm()
        return render(request, "public/password_gate.html", {"form": form})

    PublicAccessService.grant_access(request_obj, request)
    PublicAccessService.mark_accessed(request_obj, request)
    items = request_obj.items.all().order_by("id")
    session_key = request.session.session_key or ""
    # A plain link may have been forwarded, so it shows only files sent from
    # this browser; the recipient signed in to their account sees them all.
    docs = (
        GuestUploadContext.all_documents_by_item(request_obj)
        if verified
        else GuestUploadContext.own_documents_by_item(request_obj, session_key)
    )
    for item in items:
        item.own_documents = docs.get(item.id, [])
        for document in item.own_documents:
            document.can_delete = bool(
                session_key and document.uploaded_by_session_key == session_key
            )

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
    """The recipient's own panel without an account: every request sent to
    their address, open and finished, from every sender."""
    access = RecipientAccess.objects.filter(token=token).first()
    if access is None:
        raise Http404
    remember_recipient_timezone(access.email, request)
    rows, tabs = received.filtered(
        received.received_requests(access.email), request.GET.get("widok")
    )
    # Only a pointer to the panel - never a login link: this page's address
    # is in every email to the recipient, and emails get forwarded.
    account = User.objects.filter(
        email__iexact=access.email, is_active=True, email_verified_at__isnull=False
    ).first()
    account_link = None
    if account is not None and hasattr(account, "guest_access"):
        account_link = reverse("accounts:guest-link-request")
    elif account is not None and not hasattr(account, "demo_account"):
        account_link = reverse("accounts:login")
    return render(
        request,
        "public/recipient_portal.html",
        {
            "recipient_email": access.email,
            "rows": rows,
            "tabs": tabs,
            "active_view": next(t["key"] for t in tabs if t["active"]),
            "account_link": account_link,
        },
    )
