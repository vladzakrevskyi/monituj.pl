from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.forms import (
    AccountDeletionForm,
    EmailChangeForm,
    LoginForm,
    PasswordChangeForm,
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
    ProfileForm,
    RegistrationForm,
)
from apps.accounts.services import (
    AccountDeletionService,
    AuthenticationService,
    EmailChangeService,
    PasswordChangeService,
    PasswordResetService,
    ProfileService,
    RegistrationService,
    VerificationService,
)
from apps.common.exceptions import ApplicationError
from apps.common.forms import add_service_error
from apps.common.responses import (
    ajax_form_error_response,
    error_response,
    is_ajax_request,
    success_response,
)
from apps.demo.models import is_demo_user

DEMO_SETTINGS_MESSAGE = (
    "W wersji demo nie można zmieniać ustawień konta. Załóż własne konto, "
    "aby skonfigurować profil."
)


@require_http_methods(["GET", "POST"])
def register(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            try:
                RegistrationService.register(
                    email=form.cleaned_data["email"],
                    password=form.cleaned_data["password"],
                    accept_terms=form.cleaned_data["accept_terms"],
                    accept_privacy_policy=form.cleaned_data["accept_privacy_policy"],
                    request=request,
                )
                redirect_url = reverse("accounts:verification-sent")
                if is_ajax_request(request):
                    return success_response({"redirect_url": redirect_url})
                return redirect(redirect_url)
            except ApplicationError as exc:
                add_service_error(
                    form,
                    exc,
                    {
                        "EMAIL_TAKEN": "email",
                        "WEAK_PASSWORD": "password",
                        "CONSENT_REQUIRED": "accept_terms",
                    },
                )
        if is_ajax_request(request):
            return ajax_form_error_response(form)
    else:
        form = RegistrationForm()
    return render(request, "accounts/register.html", {"form": form})


def verification_sent(request):
    return render(
        request,
        "base/message.html",
        {
            "title": "Sprawdź swoją skrzynkę",
            "message": "Wysłaliśmy link weryfikacyjny na podany adres email.",
        },
    )


def verify_email(request, token):
    try:
        VerificationService.verify(token, request=request)
        context = {
            "title": "Email zweryfikowany",
            "message": (
                "Twój adres email został potwierdzony. Możesz się teraz zalogować."
            ),
        }
    except ApplicationError as exc:
        context = {"title": "Nieprawidłowy link", "message": exc.message}
    return render(request, "base/message.html", context)


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:panel")
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            try:
                AuthenticationService.login(
                    request, form.cleaned_data["email"], form.cleaned_data["password"]
                )
                redirect_url = reverse("accounts:panel")
                if is_ajax_request(request):
                    return success_response({"redirect_url": redirect_url})
                return redirect(redirect_url)
            except ApplicationError as exc:
                add_service_error(form, exc, {"INVALID_CREDENTIALS": "password"})
        if is_ajax_request(request):
            return ajax_form_error_response(form)
    else:
        form = LoginForm()
    return render(request, "accounts/login.html", {"form": form})


@require_http_methods(["POST"])
def logout_view(request):
    AuthenticationService.logout(request)
    return redirect("accounts:login")


@require_http_methods(["GET", "POST"])
def password_reset_request(request):
    if request.method == "POST":
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            PasswordResetService.request_reset(
                form.cleaned_data["email"], request=request
            )
            title = "Sprawdź swoją skrzynkę"
            message = (
                "Jeśli konto z podanym adresem email istnieje, "
                "wysłaliśmy link do resetu hasła."
            )
            if is_ajax_request(request):
                return success_response({"title": title, "message": message})
            return render(
                request, "base/message.html", {"title": title, "message": message}
            )
        if is_ajax_request(request):
            return ajax_form_error_response(form)
    else:
        form = PasswordResetRequestForm()
    return render(request, "accounts/password_reset_request.html", {"form": form})


@require_http_methods(["GET", "POST"])
def password_reset_confirm(request, token):
    if request.method == "POST":
        form = PasswordResetConfirmForm(request.POST)
        if form.is_valid():
            try:
                PasswordResetService.confirm_reset(
                    token, form.cleaned_data["password"], request=request
                )
                title = "Hasło zmienione"
                message = "Twoje hasło zostało zmienione. Możesz się teraz zalogować."
                if is_ajax_request(request):
                    return success_response({"title": title, "message": message})
                return render(
                    request, "base/message.html", {"title": title, "message": message}
                )
            except ApplicationError as exc:
                add_service_error(form, exc, {"WEAK_PASSWORD": "password"})
        if is_ajax_request(request):
            return ajax_form_error_response(form)
    else:
        form = PasswordResetConfirmForm()
    return render(
        request, "accounts/password_reset_confirm.html", {"form": form, "token": token}
    )


@login_required
def dashboard(request):
    from apps.requests.services import DashboardService

    stats = DashboardService.for_owner(request.user)
    return render(request, "accounts/dashboard.html", stats)


@login_required
@require_http_methods(["GET", "POST"])
def settings_view(request):
    profile_form = ProfileForm(initial={"display_name": request.user.display_name})
    # Both forms have a current_password field; distinct auto_ids keep the
    # HTML ids (and label targets) unique on the settings page.
    password_form = PasswordChangeForm(auto_id="id_password_%s")
    email_form = EmailChangeForm(auto_id="id_email_%s")
    deletion_form = AccountDeletionForm(auto_id="id_delete_%s")

    if request.method == "POST" and is_demo_user(request.user):
        if is_ajax_request(request):
            return error_response("DEMO_READONLY", DEMO_SETTINGS_MESSAGE, status=403)
        messages.error(request, DEMO_SETTINGS_MESSAGE)
        return redirect("accounts:settings")

    if request.method == "POST":
        action = request.POST.get("form_action")
        ajax = is_ajax_request(request)
        if action == "profile":
            profile_form = ProfileForm(request.POST)
            if profile_form.is_valid():
                ProfileService.update_profile(
                    request.user,
                    profile_form.cleaned_data["display_name"],
                    request=request,
                )
                if ajax:
                    return success_response({"message": "Dane zostały zapisane."})
                messages.success(request, "Dane zostały zapisane.")
                return redirect("accounts:settings")
            if ajax:
                return ajax_form_error_response(profile_form)
        elif action == "password":
            password_form = PasswordChangeForm(request.POST, auto_id="id_password_%s")
            if password_form.is_valid():
                try:
                    PasswordChangeService.request_change(
                        request.user,
                        password_form.cleaned_data["current_password"],
                        password_form.cleaned_data["new_password"],
                        request=request,
                    )
                    success_message = (
                        "Wysłaliśmy link potwierdzający zmianę hasła na Twój "
                        "adres email."
                    )
                    if ajax:
                        return success_response({"message": success_message})
                    messages.success(request, success_message)
                    return redirect("accounts:settings")
                except ApplicationError as exc:
                    add_service_error(
                        password_form,
                        exc,
                        {
                            "INVALID_CURRENT_PASSWORD": "current_password",
                            "WEAK_PASSWORD": "new_password",
                        },
                    )
            if ajax:
                return ajax_form_error_response(password_form)
        elif action == "email":
            email_form = EmailChangeForm(request.POST, auto_id="id_email_%s")
            if email_form.is_valid():
                try:
                    EmailChangeService.request_change(
                        request.user,
                        email_form.cleaned_data["new_email"],
                        email_form.cleaned_data["current_password"],
                        request=request,
                    )
                    success_message = (
                        "Wysłaliśmy link potwierdzający na nowy adres email."
                    )
                    if ajax:
                        return success_response({"message": success_message})
                    messages.success(request, success_message)
                    return redirect("accounts:settings")
                except ApplicationError as exc:
                    add_service_error(
                        email_form,
                        exc,
                        {
                            "INVALID_CURRENT_PASSWORD": "current_password",
                            "EMAIL_UNCHANGED": "new_email",
                            "EMAIL_TAKEN": "new_email",
                        },
                    )
            if ajax:
                return ajax_form_error_response(email_form)
        elif action == "delete":
            deletion_form = AccountDeletionForm(request.POST, auto_id="id_delete_%s")
            if deletion_form.is_valid():
                try:
                    AccountDeletionService.request_deletion(
                        request.user,
                        deletion_form.cleaned_data["current_password"],
                        request=request,
                    )
                    success_message = (
                        "Wysłaliśmy link potwierdzający usunięcie konta na "
                        f"{request.user.email}. Link jest ważny przez godzinę."
                    )
                    if ajax:
                        return success_response({"message": success_message})
                    messages.success(request, success_message)
                    return redirect("accounts:settings")
                except ApplicationError as exc:
                    add_service_error(
                        deletion_form,
                        exc,
                        {"INVALID_CURRENT_PASSWORD": "current_password"},
                    )
            if ajax:
                return ajax_form_error_response(deletion_form)

    return render(
        request,
        "accounts/settings.html",
        {
            "profile_form": profile_form,
            "password_form": password_form,
            "email_form": email_form,
            "deletion_form": deletion_form,
        },
    )


@require_http_methods(["GET", "POST"])
def password_change_confirm(request, token):
    if request.method == "POST":
        try:
            PasswordChangeService.confirm_change(token, request=request)
            return render(
                request,
                "base/message.html",
                {
                    "title": "Hasło zmienione",
                    "message": (
                        "Twoje hasło zostało zmienione. Zostałeś wylogowany ze "
                        "wszystkich urządzeń - zaloguj się ponownie nowym hasłem."
                    ),
                },
            )
        except ApplicationError as exc:
            return render(
                request,
                "base/message.html",
                {"title": "Nieprawidłowy link", "message": exc.message},
            )
    return render(request, "accounts/password_change_confirm.html", {"token": token})


@require_http_methods(["GET", "POST"])
def email_change_confirm(request, token):
    if request.method == "POST":
        try:
            EmailChangeService.confirm_change(token, request=request)
            return render(
                request,
                "base/message.html",
                {
                    "title": "Email zmieniony",
                    "message": "Twój adres email został zaktualizowany.",
                },
            )
        except ApplicationError as exc:
            return render(
                request,
                "base/message.html",
                {"title": "Nieprawidłowy link", "message": exc.message},
            )
    return render(request, "accounts/email_change_confirm.html", {"token": token})


@require_http_methods(["GET", "POST"])
def account_deletion_confirm(request, token):
    """GET only shows what will be removed; the deletion itself needs the
    button press, so link scanners in mail clients can't trigger it."""
    try:
        if request.method == "POST":
            email = AccountDeletionService.confirm(token, request=request)
            return render(
                request,
                "base/message.html",
                {
                    "title": "Konto zostało usunięte",
                    "message": (
                        "Usunęliśmy Twoje konto razem z klientami, prośbami, "
                        "przypomnieniami i przesłanymi plikami. Potwierdzenie "
                        f"wysłaliśmy na {email}."
                    ),
                },
            )
        deletion_token = AccountDeletionService.pending_token(token)
    except ApplicationError as exc:
        return render(
            request,
            "base/message.html",
            {"title": "Nieprawidłowy link", "message": exc.message},
        )
    user = deletion_token.user
    return render(
        request,
        "accounts/account_deletion_confirm.html",
        {
            "token": token,
            "account_email": user.email,
            **AccountDeletionService.summary(user),
        },
    )
