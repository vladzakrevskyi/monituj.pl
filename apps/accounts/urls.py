from django.urls import path

from apps.accounts import google_views, views

app_name = "accounts"

urlpatterns = [
    path("rejestracja/", views.register, name="register"),
    path("logowanie/", views.login_view, name="login"),
    path("logowanie/google/", google_views.google_start, name="google-start"),
    path(
        "logowanie/google/powrot/",
        google_views.google_callback,
        name="google-callback",
    ),
    path(
        "logowanie/google/potwierdz/<str:signed>/",
        google_views.google_confirm,
        name="google-confirm",
    ),
    path("rejestracja/google/", google_views.google_signup, name="google-signup"),
    path(
        "ustawienia/google/polacz/",
        google_views.google_connect,
        name="google-connect",
    ),
    path("wyloguj/", views.logout_view, name="logout"),
    path("weryfikacja-email/", views.verification_sent, name="verification-sent"),
    path("weryfikacja-email/<str:token>/", views.verify_email, name="verify-email"),
    path("reset-hasla/", views.password_reset_request, name="password-reset-request"),
    path(
        "reset-hasla/<str:token>/",
        views.password_reset_confirm,
        name="password-reset-confirm",
    ),
    path("panel/", views.dashboard, name="panel"),
    path("dostep/wyslij/", views.guest_link_request, name="guest-link-request"),
    path("dostep/e/<str:signed>/", views.guest_email_access, name="guest-email-access"),
    path("dostep/<str:token>/", views.guest_access, name="guest-access"),
    path("ustawienia/", views.settings_view, name="settings"),
    path(
        "ustawienia/haslo/potwierdz/<str:token>/",
        views.password_change_confirm,
        name="password-change-confirm",
    ),
    path(
        "ustawienia/usun-konto/potwierdz/<str:token>/",
        views.account_deletion_confirm,
        name="account-deletion-confirm",
    ),
    path(
        "ustawienia/email/potwierdz/<str:token>/",
        views.email_change_confirm,
        name="email-change-confirm",
    ),
]
