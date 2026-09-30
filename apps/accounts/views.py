from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from apps.accounts import two_factor
from apps.accounts.forms import (
    AccountDeletionForm,
    EmailChangeForm,
    GoogleConnectForm,
    LoginForm,
    PasswordChangeForm,
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
    ProfileForm,
    RegistrationForm,
    SetPasswordForm,
    TwoFactorConfirmForm,
    TwoFactorLoginForm,
    TwoFactorManageForm,
    TwoFactorPasswordForm,
)
from apps.accounts.google_auth import GoogleAuthService, GoogleConnectGate
from apps.accounts.models import is_guest_account
from apps.accounts.sender import paying_firm
from apps.accounts.services import (
    AccountDeletionService,
    AuthenticationService,
    EmailChangeService,
    GuestAccessService,
    PasswordChangeService,
    PasswordResetService,
    ProfileService,
    RegistrationService,
    VerificationService,
)
from apps.billing.services import remember_signup_plan, welcome_url
from apps.billing.services import state_for as billing_state_for
from apps.common.exceptions import ApplicationError
from apps.common.forms import add_service_error
from apps.common.responses import (
    ajax_form_error_response,
    error_response,
    is_ajax_request,
    success_response,
)
from apps.demo.models import is_demo_user
from apps.requests import request_templates

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
        request_templates.remember_for_signup(request)
    return render(
        request,
        "accounts/register.html",
        {"form": form, "signup_plan": remember_signup_plan(request)},
    )


def verification_sent(request):
    return render(
        request,
        "base/message.html",
        {
            "title": "Sprawdź swoją skrzynkę",
            "message": (
                "Wysłaliśmy wiadomość z linkiem na podany adres. Kliknij go, "
                "aby dokończyć zakładanie konta."
            ),
        },
    )


@require_http_methods(["GET", "POST"])
def verify_email(request, token):
    """The link proves the address and logs straight in. Opening it only
    shows a button: mail scanners that open links must not use up the link
    (or log themselves in), and a link someone else sent you must not
    silently swap the account you're signed in to."""
    try:
        if request.method == "GET":
            user = VerificationService.pending_user(token)
            return render(
                request,
                "accounts/verify_email.html",
                {"account_email": user.email},
            )
        user = VerificationService.verify(token, request=request)
    except ApplicationError as exc:
        return render(
            request,
            "base/message.html",
            {"title": "Nieprawidłowy link", "message": exc.message},
        )
    GuestAccessService.login(request, user)
    messages.success(request, "Adres email potwierdzony - witaj w Monituj!")
    return redirect(welcome_url(request, user))


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
                redirect_url = two_factor.pending_url(request) or reverse(
                    "accounts:panel"
                )
                if is_ajax_request(request):
                    return success_response({"redirect_url": redirect_url})
                return redirect(redirect_url)
            except ApplicationError as exc:
                add_service_error(
                    form,
                    exc,
                    {"INVALID_CREDENTIALS": "password", "EMAIL_NOT_VERIFIED": "email"},
                )
        if is_ajax_request(request):
            return ajax_form_error_response(form)
    else:
        form = LoginForm()
    return render(request, "accounts/login.html", {"form": form})


@require_http_methods(["GET", "POST"])
def two_factor_login(request):
    """The second step of signing in: the code from the app (or a backup
    code). Only for someone the first step has just let through."""
    if request.user.is_authenticated:
        return redirect("accounts:panel")
    if two_factor.pending_user(request) is None:
        messages.info(request, two_factor.EXPIRED_MESSAGE)
        return redirect("accounts:login")
    form = TwoFactorLoginForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            try:
                user, kind, next_url = two_factor.complete(
                    request, form.cleaned_data["code"]
                )
            except ApplicationError as exc:
                if exc.code == "TWO_FACTOR_EXPIRED":
                    messages.info(request, exc.message)
                    login_url = reverse("accounts:login")
                    if is_ajax_request(request):
                        return success_response({"redirect_url": login_url})
                    return redirect(login_url)
                add_service_error(
                    form, exc, {"INVALID_CODE": "code", "TWO_FACTOR_LIMIT": "code"}
                )
            else:
                if kind == "backup":
                    left = two_factor.remaining_backup_codes(user)
                    messages.warning(
                        request,
                        f"Użyto kodu zapasowego - zostało {left}. "
                        "Nowe wygenerujesz w Ustawieniach.",
                    )
                if not url_has_allowed_host_and_scheme(
                    next_url,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    next_url = reverse("accounts:panel")
                if is_ajax_request(request):
                    response = success_response({"redirect_url": next_url})
                else:
                    response = redirect(next_url)
                if form.cleaned_data["remember"]:
                    two_factor.remember_device(response, user)
                return response
        if is_ajax_request(request):
            return ajax_form_error_response(form)
    return render(request, "accounts/two_factor_login.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def two_factor_settings(request):
    """Turning two-step verification on and off, and new backup codes."""
    user = request.user
    if not two_factor.can_use(user):
        messages.error(
            request,
            DEMO_SETTINGS_MESSAGE
            if is_demo_user(user)
            else "Weryfikację dwuetapową włączysz po ustawieniu hasła.",
        )
        return redirect("accounts:settings")
    has_password = user.has_usable_password()
    enabled = two_factor.is_enabled(user)
    start_form = TwoFactorPasswordForm(require_password=has_password)
    confirm_form = TwoFactorConfirmForm()
    manage_form = TwoFactorManageForm(require_password=has_password)
    action = request.POST.get("form_action") if request.method == "POST" else None
    try:
        if action == "start" and not enabled:
            start_form = TwoFactorPasswordForm(
                request.POST, require_password=has_password
            )
            if start_form.is_valid():
                two_factor.check_password(
                    request, user, start_form.cleaned_data.get("current_password")
                )
                two_factor.start_setup(request, user)
                return redirect("accounts:two-factor")
        elif action == "confirm" and not enabled:
            confirm_form = TwoFactorConfirmForm(request.POST)
            if confirm_form.is_valid():
                codes = two_factor.confirm_setup(
                    request, user, confirm_form.cleaned_data["code"]
                )
                two_factor.keep_new_codes(request, codes)
                messages.success(request, "Weryfikacja dwuetapowa jest włączona.")
                return redirect("accounts:two-factor")
        elif action == "cancel":
            two_factor.cancel_setup(request)
            return redirect("accounts:settings")
        elif action in ("disable", "codes") and enabled:
            manage_form = TwoFactorManageForm(
                request.POST, require_password=has_password
            )
            if manage_form.is_valid():
                password = manage_form.cleaned_data.get("current_password")
                code = manage_form.cleaned_data["code"]
                if action == "codes":
                    codes = two_factor.regenerate_codes(request, user, password, code)
                    two_factor.keep_new_codes(request, codes)
                    messages.success(
                        request,
                        "Nowe kody zapasowe są gotowe. Poprzednie już nie działają.",
                    )
                    return redirect("accounts:two-factor")
                two_factor.disable(request, user, password, code)
                messages.success(request, "Weryfikacja dwuetapowa jest wyłączona.")
                response = redirect("accounts:settings")
                two_factor.forget_device(response)
                return response
    except ApplicationError as exc:
        if exc.code == "TWO_FACTOR_EXPIRED":
            messages.error(request, exc.message)
            return redirect("accounts:two-factor")
        form = {"start": start_form, "confirm": confirm_form}.get(action, manage_form)
        add_service_error(
            form,
            exc,
            {
                "INVALID_CURRENT_PASSWORD": "current_password",
                "REAUTH_LIMIT_REACHED": "current_password",
                "INVALID_CODE": "code",
                "TWO_FACTOR_LIMIT": "code",
            },
        )

    context = {
        "enabled": enabled,
        "has_password": has_password,
        "start_form": start_form,
        "confirm_form": confirm_form,
        "manage_form": manage_form,
        "new_codes": two_factor.take_new_codes(request),
    }
    if enabled:
        context["remaining_codes"] = two_factor.remaining_backup_codes(user)
    else:
        secret = two_factor.pending_setup(request, user)
        if secret:
            context["setup"] = two_factor.setup_details(user, secret)
    return render(request, "accounts/two_factor.html", context)


@require_http_methods(["POST"])
def logout_view(request):
    AuthenticationService.logout(request)
    return redirect("accounts:login")


@require_http_methods(["GET", "POST"])
def password_reset_request(request):
    if request.method == "POST":
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            try:
                PasswordResetService.request_reset(
                    form.cleaned_data["email"], request=request
                )
            except ApplicationError as exc:
                add_service_error(form, exc)
            else:
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
                user = PasswordResetService.confirm_reset(
                    token, form.cleaned_data["password"], request=request
                )
                title = "Hasło zmienione"
                message = "Twoje hasło zostało zmienione. Możesz się teraz zalogować."
                google_account = getattr(user, "google_account", None)
                if google_account is not None:
                    # Recovering an account: say plainly what else opens it.
                    message += (
                        " Do konta jest też podłączone logowanie przez Google "
                        f"({google_account.email}). Jeśli to nie Twoje konto "
                        "Google, zaloguj się i odłącz je w Ustawieniach."
                    )
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
    stats["security_hint"] = two_factor.show_hint(request.user)
    return render(request, "accounts/dashboard.html", stats)


@login_required
@require_http_methods(["POST"])
def security_hint_hide(request):
    """ "Nie teraz" on the panel's two-step verification hint."""
    if not is_demo_user(request.user):
        two_factor.hide_hint(request.user)
    if is_ajax_request(request):
        return success_response({})
    return redirect("accounts:panel")


@login_required
@require_http_methods(["GET", "POST"])
def settings_view(request):
    profile_form = ProfileForm(
        initial={
            "display_name": request.user.display_name,
            "show_paying_firm": request.user.show_paying_firm,
        }
    )
    # Both forms have a current_password field; distinct auto_ids keep the
    # HTML ids (and label targets) unique on the settings page.
    password_form = PasswordChangeForm(auto_id="id_password_%s")
    email_form = EmailChangeForm(auto_id="id_email_%s")
    guest = is_guest_account(request.user)
    # Guests and accounts created with Google have no password yet.
    has_password = request.user.has_usable_password()
    set_password_form = SetPasswordForm(auto_id="id_set_%s")
    deletion_form = AccountDeletionForm(
        auto_id="id_delete_%s", require_password=has_password
    )
    google_form = GoogleConnectForm(auto_id="id_google_%s")

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
                    show_paying_firm=profile_form.cleaned_data["show_paying_firm"],
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
        elif action == "rotate_link" and guest:
            GuestAccessService.rotate(request.user, request=request)
            success_message = (
                f"Nowy stały link wysłaliśmy na {request.user.email}. "
                "Wszystkie poprzednie linki przestały działać."
            )
            if ajax:
                return success_response({"message": success_message})
            messages.success(request, success_message)
            return redirect("accounts:settings")
        elif action == "google_connect":
            google_form = GoogleConnectForm(request.POST, auto_id="id_google_%s")
            if not has_password:
                # No password to check: the proof comes from the mailbox.
                GoogleConnectGate.send_link(request.user)
                success_message = (
                    f"Wysłaliśmy link na {request.user.email}. Otwórz go w tej "
                    "przeglądarce, aby połączyć konto z Google."
                )
                if ajax:
                    return success_response({"message": success_message})
                messages.success(request, success_message)
                return redirect("accounts:settings")
            if google_form.is_valid():
                try:
                    GoogleConnectGate.confirm_password(
                        request,
                        request.user,
                        google_form.cleaned_data["current_password"],
                    )
                    redirect_url = reverse("accounts:google-connect")
                    if ajax:
                        return success_response({"redirect_url": redirect_url})
                    return redirect(redirect_url)
                except ApplicationError as exc:
                    add_service_error(
                        google_form,
                        exc,
                        {
                            "INVALID_CURRENT_PASSWORD": "current_password",
                            "REAUTH_LIMIT_REACHED": "current_password",
                        },
                    )
            if ajax:
                return ajax_form_error_response(google_form)
        elif action == "google_disconnect":
            try:
                GoogleAuthService.disconnect(request.user, request=request)
                success_message = (
                    "Odłączono Google. Logujesz się teraz adresem email i hasłem."
                )
                if ajax:
                    return success_response(
                        {"message": success_message, "redirect_url": request.path}
                    )
                messages.success(request, success_message)
            except ApplicationError as exc:
                if ajax:
                    return error_response(exc.code, exc.message, status=400)
                messages.error(request, exc.message)
            return redirect("accounts:settings")
        elif action == "set_password" and not has_password:
            set_password_form = SetPasswordForm(request.POST, auto_id="id_set_%s")
            if set_password_form.is_valid():
                try:
                    GuestAccessService.request_password(
                        request.user,
                        set_password_form.cleaned_data["new_password"],
                        request=request,
                    )
                    success_message = (
                        f"Wysłaliśmy link potwierdzający na {request.user.email}. "
                        "Po kliknięciu zalogujesz się już hasłem."
                    )
                    if ajax:
                        return success_response({"message": success_message})
                    messages.success(request, success_message)
                    return redirect("accounts:settings")
                except ApplicationError as exc:
                    add_service_error(
                        set_password_form, exc, {"WEAK_PASSWORD": "new_password"}
                    )
            if ajax:
                return ajax_form_error_response(set_password_form)
        elif action == "delete":
            deletion_form = AccountDeletionForm(
                request.POST, auto_id="id_delete_%s", require_password=has_password
            )
            if deletion_form.is_valid():
                try:
                    AccountDeletionService.request_deletion(
                        request.user,
                        deletion_form.cleaned_data.get("current_password", ""),
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
            "set_password_form": set_password_form,
            "is_guest": guest,
            "has_password": has_password,
            "google_account": getattr(request.user, "google_account", None),
            "paying_firm": paying_firm(request.user),
            "google_form": google_form,
            "two_factor_enabled": two_factor.is_enabled(request.user),
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
        failed = exc.code == "SUBSCRIPTION_CANCEL_FAILED"
        return render(
            request,
            "base/message.html",
            {
                "title": "Nie udało się usunąć konta"
                if failed
                else "Nieprawidłowy link",
                "message": exc.message,
            },
        )
    user = deletion_token.user
    return render(
        request,
        "accounts/account_deletion_confirm.html",
        {
            "token": token,
            "account_email": user.email,
            "subscription": billing_state_for(user),
            **AccountDeletionService.summary(user),
        },
    )


def _safe_next(request):
    target = request.GET.get("next") or request.POST.get("next") or ""
    if url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return reverse("accounts:panel")


def _enter_guest_account(request, user):
    """Logs in through a panel link. If someone else is signed in in this
    browser, ask first - a link from a stranger must not silently swap the
    account you are working in."""
    if request.user == user:
        return redirect(_safe_next(request))
    if request.user.is_authenticated and request.method != "POST":
        return render(
            request,
            "accounts/guest_switch.html",
            {"target_email": user.email, "next": _safe_next(request)},
        )
    GuestAccessService.login(request, user)
    return redirect(_safe_next(request))


@require_http_methods(["GET", "POST"])
def guest_access(request, token):
    """The permanent link of an account without a password."""
    try:
        user = GuestAccessService.user_for(token)
    except ApplicationError as exc:
        return render(
            request,
            "base/message.html",
            {"title": "Link nie działa", "message": exc.message},
            status=404,
        )
    return _enter_guest_account(request, user)


@require_http_methods(["GET", "POST"])
def guest_email_access(request, signed):
    """The 14-day link from everyday emails."""
    try:
        user = GuestAccessService.user_for_email_link(signed)
    except ApplicationError as exc:
        return render(
            request,
            "accounts/guest_link_expired.html",
            {
                "message": exc.message,
                # The expired link itself asks for a new one - the address
                # it belongs to is never shown to whoever holds the link.
                "signed": signed if getattr(exc, "user", None) else "",
            },
            status=404,
        )
    return _enter_guest_account(request, user)


@require_http_methods(["GET", "POST"])
def guest_link_request(request):
    """Sends the permanent panel link again - for anyone who lost it."""
    sent = False
    error = ""
    email = request.POST.get("email", "").strip() if request.method == "POST" else ""
    signed = request.POST.get("signed", "") if request.method == "POST" else ""
    if request.method == "POST":
        try:
            if signed:
                GuestAccessService.resend_for_expired_link(signed, request=request)
            else:
                GuestAccessService.send_access_link(email, request=request)
            sent = True
        except ApplicationError as exc:
            error = exc.message
    return render(
        request,
        "accounts/guest_link_request.html",
        {"sent": sent, "error": error, "email": email},
    )
