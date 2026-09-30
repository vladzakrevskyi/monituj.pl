from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.accounts import google, two_factor
from apps.accounts.forms import GoogleSignupForm
from apps.accounts.google_auth import (
    GoogleAuthService,
    GoogleConnectGate,
    Outcome,
    consume_attempt,
)
from apps.billing.services import welcome_url
from apps.common.exceptions import ApplicationError
from apps.common.forms import add_service_error
from apps.common.responses import (
    ajax_form_error_response,
    error_response,
    is_ajax_request,
    success_response,
)
from apps.demo.models import is_demo_user

TITLE = "Logowanie przez Google"


def _require_enabled():
    if not google.enabled():
        raise Http404


CHECK_INBOX_TITLE = "Sprawdź swoją skrzynkę"


def _problem(request, message, status=400):
    # The terms form posts in the background: it needs JSON to show the
    # message - an HTML page would leave it silently where it was.
    if is_ajax_request(request):
        return error_response("GOOGLE_SIGNUP", message, status=status)
    return render(
        request,
        "accounts/google_problem.html",
        {"title": TITLE, "message": message},
        status=status,
    )


def _check_inbox(request, email):
    if is_ajax_request(request):
        # The form turns into this message (data-replace-on-success).
        return success_response(
            {
                "title": CHECK_INBOX_TITLE,
                "message": (
                    f"Wysłaliśmy link potwierdzający na {email}. Otwórz go w tej "
                    "przeglądarce w ciągu 30 minut - potem logowanie przez Google "
                    "zadziała od razu. Prosimy o to, bo Google nie prowadzi tej "
                    "skrzynki, więc sprawdzamy, że nadal należy do Ciebie."
                ),
            }
        )
    return render(
        request,
        "accounts/google_check_inbox.html",
        {"email": email, "title": CHECK_INBOX_TITLE},
    )


def google_start(request):
    _require_enabled()
    if request.user.is_authenticated:
        return redirect("accounts:panel")
    return redirect(google.authorization_url(request, "login"))


@login_required
def google_connect(request):
    _require_enabled()
    if is_demo_user(request.user):
        messages.error(request, "W wersji demo nie można łączyć konta z Google.")
        return redirect("accounts:settings")
    if hasattr(request.user, "google_account"):
        return redirect("accounts:settings")
    if not GoogleConnectGate.take(request):
        messages.error(
            request, "Najpierw potwierdź, że to Ty - w Ustawieniach, przy Google."
        )
        return redirect(reverse("accounts:settings") + "#google")
    return redirect(google.authorization_url(request, "connect", user=request.user))


@login_required
@require_http_methods(["GET", "POST"])
def google_connect_confirm(request, signed):
    """The link from the "confirm adding Google" email (accounts without a
    password). Opening it only shows a button."""
    _require_enabled()
    if request.method == "GET":
        return render(request, "accounts/google_connect_confirm.html")
    try:
        GoogleConnectGate.confirm_link(request, signed)
    except ApplicationError as exc:
        return _problem(request, exc.message)
    return redirect("accounts:google-connect")


def google_callback(request):
    _require_enabled()
    flow = google.take_flow(request)
    connecting = bool(flow and flow.get("intent") == "connect")
    if request.GET.get("error"):
        # The person closed Google's window or said no - not an error.
        messages.info(request, "Logowanie przez Google zostało przerwane.")
        return redirect("accounts:settings" if connecting else "accounts:login")
    try:
        google.check_state(flow, request.GET.get("state", ""))
        consume_attempt(request)
        identity = google.identity_from_callback(flow, request.GET.get("code", ""))
        if connecting:
            user = request.user
            if not user.is_authenticated or user.pk != flow.get("user"):
                return _problem(request, google.EXPIRED_MESSAGE)
            GoogleAuthService.connect(user, identity, request)
            messages.success(
                request,
                f"Połączono z kontem Google {identity.email}. Możesz się nim logować.",
            )
            return redirect("accounts:settings")
        outcome, result = GoogleAuthService.sign_in(request, identity)
    except ApplicationError as exc:
        if connecting and request.user.is_authenticated:
            messages.error(request, exc.message)
            return redirect("accounts:settings")
        return _problem(request, exc.message, status=exc.status_code or 400)
    if outcome is Outcome.SIGNUP:
        return redirect("accounts:google-signup")
    if outcome is Outcome.CONFIRM_SENT:
        return _check_inbox(request, result)
    return redirect(two_factor.pending_url(request) or "accounts:panel")


@require_http_methods(["GET", "POST"])
def google_signup(request):
    """The last step of signing up with Google: the terms, like in the
    password form - an account never starts without them."""
    _require_enabled()
    try:
        identity = GoogleAuthService.pending_signup(request)
    except ApplicationError as exc:
        return _problem(request, exc.message)
    form = GoogleSignupForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                outcome, result = GoogleAuthService.complete_signup(
                    request,
                    form.cleaned_data["accept_terms"],
                    form.cleaned_data["accept_privacy_policy"],
                )
            except ApplicationError as exc:
                if exc.code == "GOOGLE_SIGNUP" or exc.code == "EMAIL_TAKEN":
                    return _problem(request, exc.message)
                add_service_error(form, exc, {"CONSENT_REQUIRED": "accept_terms"})
            else:
                if outcome is Outcome.CONFIRM_SENT:
                    return _check_inbox(request, result)
                messages.success(request, "Konto założone - witaj w Monituj!")
                redirect_url = welcome_url(request, request.user)
                if is_ajax_request(request):
                    return success_response({"redirect_url": redirect_url})
                return redirect(redirect_url)
        if is_ajax_request(request):
            return ajax_form_error_response(form)
    return render(
        request,
        "accounts/google_signup.html",
        {"form": form, "google_email": identity.email},
    )


@require_http_methods(["GET", "POST"])
def google_confirm(request, signed):
    """The link from the confirmation email. Opening it only shows a button,
    so mail scanners that open links can't use it up."""
    _require_enabled()
    try:
        if request.method == "GET":
            data = GoogleAuthService.pending_confirmation(signed)
            return render(
                request,
                "accounts/google_confirm.html",
                {"google_email": data["g"], "new_account": data["u"] is None},
            )
        GoogleAuthService.confirm(request, signed)
    except ApplicationError as exc:
        return _problem(request, exc.message)
    messages.success(request, "Gotowe - od teraz możesz logować się przez Google.")
    return redirect(two_factor.pending_url(request) or "accounts:panel")
