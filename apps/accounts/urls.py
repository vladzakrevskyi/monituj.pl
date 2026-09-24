from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("rejestracja/", views.register, name="register"),
    path("logowanie/", views.login_view, name="login"),
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
