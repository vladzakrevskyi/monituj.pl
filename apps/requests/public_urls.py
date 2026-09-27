from django.urls import path

from apps.requests import public_views

app_name = "public"

urlpatterns = [
    path("d/<str:token>/", public_views.public_request_detail, name="request-detail"),
    path(
        "d/<str:token>/moje-pliki/",
        public_views.recipient_files_request,
        name="recipient-files",
    ),
    path(
        "d/<str:token>/moje-pliki/<str:signed>/",
        public_views.recipient_files_confirm,
        name="recipient-files-confirm",
    ),
    path(
        "wyslij-prosbe/", public_views.guest_request_create, name="guest-request-create"
    ),
    path(
        "wyslij-prosbe/sprawdz-skrzynke/",
        public_views.guest_request_sent,
        name="guest-request-sent",
    ),
    path(
        "wyslij-prosbe/potwierdz/<str:token>/",
        public_views.guest_request_confirm,
        name="guest-request-confirm",
    ),
    path(
        "moje-prosby/<str:token>/",
        public_views.recipient_portal,
        name="recipient-portal",
    ),
]
